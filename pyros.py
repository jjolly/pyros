#!/usr/bin/python

import os, sys, gc
from stat import *
import argparse
import zipfile
import zlib
import struct
import pickle
import tempfile
import xml.etree.ElementTree as ET
from multiprocessing import Pool

# Recursive directory lister
# Equivalent to 'find . -type f'
def list_all_files(src_list):
    filelist = []
    for src in src_list:
        try:
            srcstat = os.stat(src)
        except:
            continue
        else:
            src_mode = srcstat.st_mode
            src_size = srcstat.st_size
            src_mtime = srcstat.st_mtime
            if S_ISDIR(src_mode):
                filelist.extend(list_all_files([src + "/" + f for f in os.listdir(src)]))
            else:
                filelist.append((src, src_size, src_mtime))
    return filelist

# Creates a dictionary of (crc, size) for every file in a list,
# mapping them to the file associated to the crc and size
# CRC collisions are easy, but linking it with the file size should
# mitigate the problem. I suppose we could go to SHA1. Yeah, right.
def collect_size_crc(src, cachepath):
    files = {}

    savecache = False

    if cachepath:
        try:
            cache = pickle.load(open(cachepath))
        except:
            cache = {}
            savecache = True
    else:
        cache = None

    filelist = list_all_files(src)
    count = 0
    total = len(filelist)

    for f, s, m in filelist:
        count += 1
        print >> sys.stderr, '\rReading source {0}/{1}'.format(count, total),
        f_stat = os.stat(f)
        # I'm not sure this caching is useful.
        if cache != None:
            if cache.has_key(f):
                if cache[f]["size"] == f_stat.st_size and cache[f]["mtime"] == f_stat.st_mtime:
                    for crc32, size, base, name in cache[f]["roms"]:
                        filekey = (crc32, size)
                        if not files.has_key(filekey):
                            files[filekey] = (base, name)
                    continue
            else:
                cache[f] = {"size": f_stat.st_size, "mtime": f_stat.st_mtime, "roms": []}
                savecache = True
        try:
            # Don't trust the filename. Treat it like a zip until it stops
            # looking like a zip.
            with zipfile.ZipFile(f, 'r') as srczip:
                for info in srczip.infolist():
                    if cache != None:
                        cache[f]["roms"].append((info.CRC, info.file_size, f, info.filename))
                        savecache = True
                    filekey = (info.CRC, info.file_size)
                    if files.has_key( filekey ):
                        continue
                    files[(info.CRC, info.file_size)] = (f, info.filename)
        except zipfile.BadZipfile:
            # OK, I guess that wasn't a zipfile. Treat it as if it were
            # uncompressed. This means 7zips will be ignored.
            try:
                size = os.stat(f).st_size
                crc32 = zlib.crc32(open(f).read())
                if cache != None:
                    cache[f]["roms"].append((crc32, size, None, f))
                    savecache = True
                files[(crc32, size)] = (None, f)
            except OSError:
                print >> sys.stderr, "Bad file " + f + ", skipping"

    print >> sys.stderr, ""

    if savecache == True and cache != None and cachepath:
        pickle.dump(cache, open(cachepath,mode='w'), pickle.HIGHEST_PROTOCOL)

    filelist = None
    cache = None

    return files

# Walks a datfile, checking if the entry has a matching file.
# Outputs a list of games, each game with a list of roms, in order.
def find_files_for_dat(dat, srcs, cachepath):
    srclist = collect_size_crc(srcs, cachepath)
    dattree = ET.parse(dat)
    datroot = dattree.getroot()

    newgames = {}

    if datroot.tag == "datafile":
        # Looking for "machine" or "game". Any others?
        # This is where the listxml support would need to come in.
        for machine in [m for m in datroot if m.tag == "machine" or m.tag == "game"]:
            mname = machine.attrib["name"].strip()
            clonename = None
            if machine.attrib.has_key("cloneof"):
                clonename = mname
                mname = machine.attrib["cloneof"].strip()
            newroms = {}
            # Here's where only merged sets are handled.
            # Could easily be fixed to handle split or non-merged sets
            if newgames.has_key(mname):
                newroms = newgames[mname]
            for rom in [r for r in machine if r.tag == "rom"]:
                # Ignore nodump. Any others?
                if rom.attrib.has_key("status") and rom.attrib["status"] == "nodump":
                    continue
                # How can we screw up the rom filename, let me count the ways
                # Datfiles use backslashed, zips use forward slashes
                # Datfiles put spaces before and after filenames. Spaces!
                romname = "/".join([x.strip() for x in rom.attrib["name"].replace("\\", "/").split("/")])
                # Datfiles will add a period to the end of the filename
                # but when the zip is created, that dot is gone.
                while romname[-1] == '.':
                    romname = romname[:-1]
                # Datefiles will use both base 10 and base 16 values for size
                try:
                    romsize = int(rom.attrib["size"])
                except ValueError:
                    romsize = int(rom.attrib["size"], base=16)
                # At least CRCs are normal
                romcrc = int(rom.attrib["crc"], base=16)
                # Check for duplicate filenames. This is important for merged sets
                romdups = [x for x in newroms.keys() if x.lower() == romname.lower()]
                dupfound = False
                namefixed = False
                for dupname in romdups:
                    if newroms[dupname]["size"] == romsize and newroms[dupname]["crc"] == romcrc:
                        # Yup, dup name and file. Just skip it.
                        dupname = romdups[0]
                        dupsize = newroms[dupname]["size"]
                        dupcrc = newroms[dupname]["crc"]
                        print >> sys.stderr, "In game {0},".format(machine.attrib["name"]),
                        print >> sys.stderr, "skipping {0}({1}:{2:08X})".format(romname, romsize, romcrc),
                        print >> sys.stderr, "as duplicate of {0}({1}:{2:08X})".format(dupname, dupsize, dupcrc)
                        dupfound = True
                    else:
                        # Dup filename, but not file content. Add a path element
                        # to the romname to make it "unique"
                        if newroms[dupname]["clonename"] != None:
                            # This is a dup in another clone. Rename the other
                            # clone as well
                            newromname = newroms[dupname]["clonename"] + '/' + dupname
                            print "Renaming {0} to {1}".format(dupname, newromname)
                            newroms[newromname] = newroms[dupname]
                            newroms[newromname]["clonename"] = None
                            del newroms[dupname]
                        if not namefixed:
                            # Now you're unique, just like everyone else
                            print "Saving {0} in {1}".format(romname, machine.attrib["name"].strip()),
                            romname = machine.attrib["name"].strip() + '/' + romname
                            print "to {0} in {1}".format(romname, mname)
                if dupfound and not namefixed:
                    continue
                romkey = (romcrc, romsize)
                if srclist.has_key(romkey):
                    newroms[romname] = {"size": romsize, "crc": romcrc, "base": srclist[romkey][0], "file": srclist[romkey][1], "clonename": clonename}
                else:
                    newroms[romname] = {"size": romsize, "crc": romcrc, "base": None, "file": None, "clonename": clonename}
            newgames[mname] = newroms
    # Hood's Balls! This is horrible! Sack the twerp that wrote this!
    return [{"machine": x, "roms": sorted([{"name": y, "size": newgames[x][y]["size"], "crc": newgames[x][y]["crc"], "base": newgames[x][y]["base"], "file": newgames[x][y]["file"]} for y in newgames[x]], key=lambda x: str.lower(x["name"]))} for x in newgames]

# Take a game with a list of roms and build a torrentzip
# Using the zipfile module is not possible, as there is not enough control
# over the compresion type and dictionary content to properly create a
# torrentzip file.
def make_zips_from_game(dest, game):
    mname = game["machine"]
    roms = game["roms"]
    if len(roms) == 0:
        return
    mpath = os.path.join(dest, mname + '.zip')
    tmpdir = None
    tmpfile = None
    # If a file exists at the path of our future zipfile, then be polite and save
    # it. It might contain something useful.
    if os.path.exists(mpath):
        try:
            with zipfile.ZipFile(mpath, 'r') as srczip:
                # If the zip on disk matches what we need to write, then skip this
                # file entirely. We're done.
                if all(map(lambda x, y: x["name"] == y.filename and x["crc"] == y.CRC and x["size"] == y.file_size, roms, srczip.infolist())):
                    return
            # Move it to a temp directory and keep it's data around. Maybe we
            # can use it's contents.
            tmpdir = tempfile.mkdtemp(dir=dest)
            tmpfile = os.path.join(tmpdir, mname + ".zip")
            os.rename(mpath, tmpfile)
            tmproms = {}
            with zipfile.ZipFile(tmpfile, 'r') as tmpzip:
                for tmprom in tmpzip.infolist():
                    tmproms[(tmprom.CRC, tmprom.file_size)] = tmprom.filename
            for rom in roms:
                # Well, whaddaya know. A rom was in the datfile, but we couldn't
                # find a match. Good thing we found one here or we would have
                # had an incomplete set. ;-)
                if rom["file"] == None and tmproms.has_key((rom["crc"], rom["size"])):
                    rom["base"] = tmpfile
                    rom["file"] = tmproms[(rom["crc"], rom["size"])]
        except:
            pass

    mzip = open(mpath, 'w')
    centdir = ""
    count = 0
    for rom in roms:
        romname = rom["name"]
        romsize = rom["size"]
        rombase = rom["base"]
        romfile = rom["file"]
        data = '\0' * romsize
        if rombase == None:
            data = open(romfile).read()
        else:
            data = zipfile.ZipFile(rombase, 'r').open(romfile).read()
        # See, it's activities like this where I end up needing to multiprocess
        # my apps. I probably could make this run much faster if I just read the
        # CRC from the previous zip. Perhaps I'm just letting my trust issues
        # get in my way.
        crc = zlib.crc32(data)
        # What?! Negative CRCs? This is absurd!
        if crc < 0:
            crc += 2**32
        # In order to get the best compression, a compressobj needs to be
        # created. Wouldn't it be nice if this was selectable from the zipfile
        # helper functions. :P
        cobj = zlib.compressobj(9, zlib.DEFLATED, -15)
        zipdata = cobj.compress(data) + cobj.flush()
        # Header for file
        header = struct.pack("<4bHHHHHLLLHH{0}s".format(len(romname)), 80, 75, 3, 4, 20, 2, 8,
                             48128, 8600, crc, len(zipdata), len(data), len(romname), 0, romname)
        # Header for central directory. Accumulate here so a CRC can be generated.
        centdir += struct.pack("<4BHHHHHHLLLHHHHHLL{0}s".format(len(romname)), 80,
                               75, 1, 2, 0, 20, 2, 8, 48128, 8600, crc, len(zipdata),
                               len(data), len(romname), 0, 0, 0, 0, 0, mzip.tell(), romname)
        mzip.write(header)
        mzip.write(zipdata)
        count += 1
    crc = zlib.crc32(centdir)
    # Somedays I miss C with it's quite reasonable unsigned int
    if crc < 0:
        crc += 2**32
    # Zipfile footer with TORRENTZIPPED comment
    footer = struct.pack("<4BHHHHLLH22s", 80, 75, 05, 06, 0, 0, count, count, len(centdir),
                         mzip.tell(), 22, "TORRENTZIPPED-{0:08X}".format(crc))
    mzip.write(centdir)
    mzip.write(footer)

    # Remove previous file if it was kept around.
    if tmpfile != None:
        os.remove(tmpfile)
    if tmpdir != None:
        os.rmdir(tmpdir)

# Helper class to allow us to multiprocess the zipfile writer
class ZipMaker(object):
    def __init__(self, dest):
        self.dest = dest
    def __call__(self, game):
        make_zips_from_game(self.dest, game)

if __name__ == '__main__':
    pool = Pool()

    aparse = argparse.ArgumentParser(description="Process TorrentZipped Romsets")
    aparse.add_argument('-sc', '--source-cache', help="Save source cache to file")
    aparse.add_argument('dest', help="Destination directory for romset")
    aparse.add_argument('dat', help="Romset DAT file")
    aparse.add_argument('src', nargs='+', help="Source files or directories")

    args = aparse.parse_args()

    if not os.path.isdir(args.dest):
        os.mkdir(args.dest)


    print >> sys.stderr, "Matching..."
    games = find_files_for_dat(args.dat, [os.path.normpath(x) for x in args.src], args.source_cache)
    print >> sys.stderr, "Writing..."
    pool.map(ZipMaker(args.dest), games)
