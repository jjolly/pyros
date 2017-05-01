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

def collect_size_crc(src, cachepath):
    files = { }

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

def find_files_for_dat(dat, srcs, cachepath):
    srclist = collect_size_crc(srcs, cachepath)
    dattree = ET.parse(dat)
    datroot = dattree.getroot()

    newgames = {}

    if datroot.tag == "datafile":
        for machine in [m for m in datroot if m.tag == "machine" or m.tag == "game"]:
            mname = machine.attrib["name"].strip()
            clonename = None
            if machine.attrib.has_key("cloneof"):
                clonename = mname
                mname = machine.attrib["cloneof"].strip()
            newroms = {}
            if newgames.has_key(mname):
                newroms = newgames[mname]
            for rom in [r for r in machine if r.tag == "rom"]:
                if rom.attrib.has_key("status") and rom.attrib["status"] == "nodump":
                    continue
                romname = "/".join([x.strip() for x in rom.attrib["name"].replace("\\", "/").split("/")])
                while romname[-1] == '.':
                    romname = romname[:-1]
                try:
                    romsize = int(rom.attrib["size"])
                except ValueError:
                    romsize = int(rom.attrib["size"], base=16)
                romcrc = int(rom.attrib["crc"], base=16)
                romdups = [x for x in newroms.keys() if x.lower() == romname.lower()]
                dupfound = False
                namefixed = False
                for dupname in romdups:
                    if newroms[dupname]["size"] == romsize and newroms[dupname]["crc"] == romcrc:
                        dupname = romdups[0]
                        dupsize = newroms[dupname]["size"]
                        dupcrc = newroms[dupname]["crc"]
                        print >> sys.stderr, "In game {0},".format(machine.attrib["name"]),
                        print >> sys.stderr, "skipping {0}({1}:{2:08X})".format(romname, romsize, romcrc),
                        print >> sys.stderr, "as duplicate of {0}({1}:{2:08X})".format(dupname, dupsize, dupcrc)
                        dupfound = True
                    else:
                        if newroms[dupname]["clonename"] != None:
                            newromname = newroms[dupname]["clonename"] + '/' + dupname
                            print "Renaming {0} to {1}".format(dupname, newromname)
                            newroms[newromname] = newroms[dupname]
                            newroms[newromname]["clonename"] = None
                            del newroms[dupname]
                        if not namefixed:
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
    return [{"machine": x, "roms": sorted([{"name": y, "size": newgames[x][y]["size"], "crc": newgames[x][y]["crc"], "base": newgames[x][y]["base"], "file": newgames[x][y]["file"]} for y in newgames[x]], key=lambda x: str.lower(x["name"]))} for x in newgames]

def make_zips_from_game(dest, game):
    mname = game["machine"]
    roms = game["roms"]
    if len(roms) == 0:
        return
    mpath = os.path.join(dest, mname + '.zip')
    tmpdir = None
    tmpfile = None
    if os.path.exists(mpath):
        try:
            with zipfile.ZipFile(mpath, 'r') as srczip:
                if all(map(lambda x, y: x["name"] == y.filename and x["crc"] == y.CRC and x["size"] == y.file_size, roms, srczip.infolist())):
                    return
            tmpdir = tempfile.mkdtemp(dir=dest)
            tmpfile = os.path.join(tmpdir, mname + ".zip")
            os.rename(mpath, tmpfile)
            tmproms = {}
            with zipfile.ZipFile(tmpfile, 'r') as tmpzip:
                for tmprom in tmpzip.infolist():
                    tmproms[(tmprom.CRC, tmprom.file_size)] = tmprom.filename
            for rom in roms:
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
        crc = zlib.crc32(data)
        if crc < 0:
            crc += 2**32
        cobj = zlib.compressobj(9, zlib.DEFLATED, -15)
        zipdata = cobj.compress(data) + cobj.flush()
        header = struct.pack("<4bHHHHHLLLHH{0}s".format(len(romname)), 80, 75, 3, 4, 20, 2, 8,
                             48128, 8600, crc, len(zipdata), len(data), len(romname), 0, romname)
        centdir += struct.pack("<4BHHHHHHLLLHHHHHLL{0}s".format(len(romname)), 80,
                               75, 1, 2, 0, 20, 2, 8, 48128, 8600, crc, len(zipdata),
                               len(data), len(romname), 0, 0, 0, 0, 0, mzip.tell(), romname)
        mzip.write(header)
        mzip.write(zipdata)
        count += 1
    crc = zlib.crc32(centdir)
    if crc < 0:
        crc += 2**32
    footer = struct.pack("<4BHHHHLLH22s", 80, 75, 05, 06, 0, 0, count, count, len(centdir),
                         mzip.tell(), 22, "TORRENTZIPPED-{0:08X}".format(crc))
    mzip.write(centdir)
    mzip.write(footer)

    if tmpfile != None:
        os.remove(tmpfile)
    if tmpdir != None:
        os.rmdir(tmpdir)

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
