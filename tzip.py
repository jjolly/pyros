#!/usr/bin/python3
import os
import io
import argparse
import zipfile
import zlib
import struct

def copy_file_to_zip(filename, zfile, srcfile, srcount):
    # In order to get the best compression, a compressobj needs to be
    # created. Wouldn't it be nice if this was selectable from the zfile
    # helper functions. :P
    cobj = zlib.compressobj(9, zlib.DEFLATED, -15)
    crc = 0
    zipdatalen = 0
    rawdatalen = 0

    # Initial header for file, to fill in space
    headerpos = zfile.tell()
    header = struct.pack("<4bHHHHHLLLHH{0}s".format(len(filename)), 80, 75, 3, 4, 20, 2, 8,
                         48128, 8600, crc, zipdatalen, rawdatalen, len(filename), 0, filename)
    zfile.write(header)

    # I choose 16M buffers because reasons. This would make a wonderful configurable parameter.
    BUFFER_LIMIT = 4096 * 4096 #2m55s

    # Read the file in chunks. This keeps memory usage reasonable, especially with roms like
    # hapyfsh2.
    while True:
        # srcfile is None when neither a zfile or a binary file was found
        if srcfile == None:
            # Create a block of zeros
            if srcount - rawdatalen < BUFFER_LIMIT:
                data = b'\0' * (srcount - rawdatalen)
            else:
                data = b'\0' * BUFFER_LIMIT
        else:
            data = srcfile.read(BUFFER_LIMIT)

        if len(data) == 0:
            break;

        crc = zlib.crc32(data, crc)

        rawdatalen += len(data)
        zipdata = cobj.compress(data)
        zfile.write(zipdata)
        zipdatalen += len(zipdata)

    zipdata = cobj.flush()
    zfile.write(zipdata)
    zipdatalen += len(zipdata)

    # Keep track of where we start, because it's time to go back.
    nextfilepos = zfile.tell()

    # What?! Negative CRCs? This is absurd!
    if crc < 0:
        crc += 2**32

    # Header for file
    header = struct.pack("<4bHHHHHLLLHH{0}s".format(len(filename)), 80, 75, 3, 4, 20, 2, 8,
                         48128, 8600, crc, zipdatalen, rawdatalen, len(filename), 0, filename)
    # Head back in the file to write the completed header
    zfile.seek(headerpos)
    zfile.write(header)

    # ...and head forward to start the next file (or the catalog, we're not picky)
    zfile.seek(nextfilepos)

    return crc, zipdatalen, rawdatalen

def add_files_to_zip(zfile, centdir, count, roms):
    for rom in roms:
        romname = rom["name"]
        romsize = rom["size"]
        rombase = rom["base"]
        romfile = rom["file"]

        rombytes = romname.encode(encoding='UTF-8')

        srcfile = None
        if rombase == None:
            if romfile != None:
                srcfile = open(romfile, 'rb')
        else:
            srcfile = zipfile.ZipFile(rombase, 'r').open(romfile)

        headerpos = zfile.tell()

        crc, zipdatalen, rawdatalen = copy_file_to_zip(rombytes, zfile, srcfile, romsize)

        # Header for central directory. Accumulate here so a CRC can be generated.
        centdir += struct.pack("<4BHHHHHHLLLHHHHHLL{0}s".format(len(rombytes)), 80,
                               75, 1, 2, 0, 20, 2, 8, 48128, 8600, crc, zipdatalen, rawdatalen,
                               len(rombytes), 0, 0, 0, 0, 0, headerpos, rombytes)
        count += 1
    crc = zlib.crc32(centdir)
    # Somedays I miss C with it's quite reasonable unsigned int
    if crc < 0:
        crc += 2**32
    combytes = "TORRENTZIPPED-{0:08X}".format(crc).encode('UTF-8')
    if len(combytes) != 22:
        raise UnicodeEncodeError
    # Zipfile footer with TORRENTZIPPED comment
    footer = struct.pack("<4BHHHHLLH22s", 80, 75, 5, 6, 0, 0, count, count, len(centdir), zfile.tell(), 22, combytes)
    zfile.write(centdir)
    zfile.write(footer)

def create_zip_from_files(zippath, roms):
    zfile = open(zippath, 'wb')
    add_files_to_zip(zfile, b'', 0, roms)

def test_zipfile(zippath):
    pass

def add_file_to_zip(zippath, fname, sname, sfname):
    files = [{"name": fname, "size": 0, "base": sname, "file": sfname}]
    if not os.path.exists(zippath):
        create_zip_from_files(zippath, files)
    else:
        zfile = open(zippath, 'r+b')
        centdir = b''
        count = 0
        zfile.seek(0, io.SEEK_END)
        if zfile.tell() > 44:
            zfile.seek(-44, io.SEEK_CUR)
            data = zfile.read(44)
            footer = struct.unpack("<4BHHHHLLH22s", data)
            count = footer[7]
            zfile.seek(footer[9], io.SEEK_SET)
            centdir = zfile.read(footer[8])
            zfile.seek(footer[9], io.SEEK_SET)

        add_files_to_zip(zfile, centdir, count, files)

if __name__ == '__main__':
    aparse = argparse.ArgumentParser(description="Torrentzip Manager")
    aparse.add_argument("zipfile")
    aparse.add_argument("filename", nargs='?')
    aparse.add_argument("srcfile", nargs='?')
    aparse.add_argument("fileinsrc", nargs='?')

    args = aparse.parse_args()

    if args.filename == None:
        test_zipfile(args.zipfile)
    else:
        filename = args.filename
        srcfile = filename
        basename = None

        if args.srcfile != None:
            srcfile = args.srcfile

            if args.fileinsrc != None:
                basename = srcfile
                srcfile = args.fileinsrc

        add_file_to_zip(args.zipfile, filename, basename, srcfile)
