#!/usr/bin/python3

import os, sys, gc
import argparse
import struct
import zipfile
import zlib
import hashlib
import xml.etree.ElementTree as ET
import types # For binding seek and tell to ZipExtFile

def validateZipFile(zh):
    files = {}
    entries = {}
    cdstart = 0
    cdend = 0
    zh.seek(0)
    while True:
        recpos = zh.tell()
        data = zh.read(4)
        if data == b'PK\x03\x04':
            # Local file header
            if len(entries) > 0:
                raise zipfile.BadZipFile("Local file header found after central directory at {}".format(recpos))
            rec = struct.unpack('<5H3L2H', zh.read(26))
            if rec[1] & 1 << 3 != 0:
                raise zipfile.BadZipFile("Zip data descriptor record at {} not supported".format(recpos))
            if rec[1] & 1 != 0 and rec[1] & 1 << 6 != 0:
                raise zipfile.BadZipFile("Strong encryption at {} not supported".format(recpos))
            if rec[1] & 1 << 13 != 0:
                raise zipfile.BadZipFile("Encryption masking at {} not supported".format(recpos))
            if rec[8] == 0:
                raise zipfile.BadZipFile("Streaming zip at {} not supported. Filename expected".format(recpos))
            fname = zh.read(rec[8])
            if fname in files:
                raise zipfile.BadZipFile("Filename '{}' already exists".format(fname))
            fsize = rec[7]
            zsize = rec[6]
            crc32 = rec[5]
            extdata = b''
            if rec[9] > 0:
                extdata = zh.read(rec[9])
            if (1 << 32) - 1 == fsize:
                i = 0
                while True:
                    if len(extdata) < i + 4:
                        raise zipfile.BadZipFile("ZIP64 extended data not found in central directory at {}".format(recpos))
                    extid, extlen = struct.unpack('<2H', extdata[i:i+4])
                    if extid == 1 and len(extdata) >= i + 12:
                        fsize = struct.unpack('<Q', extdata[i+4:i+12])[0]
                        if (1 << 32) - 1 == zsize and len(extdata) >= i + 20:
                            zsize = struct.unpack('<Q', extdata[i+12:i+20])[0]
                        break
                    i += extlen + 4
            files[fname] = {"filesize": fsize, "zipsize": zsize, "crc32": crc32}
            zh.seek(zsize, 1)
        elif data == b'PK\x01\x02':
            # Central directory entry
            if cdstart == 0:
                cdstart = recpos
            rec = struct.unpack('<6H3L5H2L', zh.read(42))
            fname = zh.read(rec[9])
            if fname not in files:
                raise zipfile.BadZipFile("Central directory filename '{}' at {} not found in files".format(fname, recpos))
            fsize = rec[8]
            zsize = rec[7]
            crc32 = rec[6]
            extdata = b''
            if rec[10] > 0:
                extdata = zh.read(rec[10])
            if (1 << 32) - 1 == fsize:
                i = 0
                while True:
                    if len(extdata) < i + 4:
                        raise zipfile.BadZipFile("ZIP64 extended data not found in central directory at {}".format(recpos))
                    extid, extlen = struct.unpack('<2H', extdata[i:i+4])
                    if extid == 1 and len(extdata) >= i + 12:
                        fsize = struct.unpack('<Q', extdata[i+4:i+12])[0]
                        if (1 << 32) - 1 == zsize and len(extdata) >= i + 20:
                            zsize = struct.unpack('<Q', extdata[i+12:i+20])[0]
                        break
                    i += extlen + 4
            if files[fname]["filesize"] != fsize:
                raise zipfile.BadZipFile("File '{}' size '{}' does not match '{}' at {}".format(fname, files[fname]["filesize"], fsize, recpos))
            if files[fname]["zipsize"] != zsize:
                raise zipfile.BadZipFile("Compress '{}' size '{}' does not match '{}' at {}".format(fname, files[fname]["zipsize"], zsize, recpos))
            if files[fname]["crc32"] != crc32:
                raise zipfile.BadZipFile("File '{}' crc32 '{:08x}' does not match '{:08x}' at {}".format(fname, files[fname]["crc32"], crc32, recpos))
            entries[fname] = files[fname]
            del files[fname]
            zh.seek(rec[11], 1)
            cdend = zh.tell()
        elif data == b'PK\x05\x06':
            # End central directory
            if 0 != len(files):
                raise zipfile.BadZipFile("Number of local files ({}) does not match number of central directory entries ({})".format(len(files) + len(entries), len(entries)))
            cdlen = cdend - cdstart
            rec = struct.unpack('<4H2LH', zh.read(18))
            if len(entries) != rec[3]:
                raise zipfile.BadZipFile("File count ({}) does not match central directory end record ({})".format(i, rec[3]))
            if cdlen != rec[4]:
                raise zipfile.BadZipFile("Central directory length ({}) does not match central directory end record ({})".format(cdlen, rec[4]))
            break
        elif data == b'PK\x06\x06':
            # zip64 end central directory
            z64len = struct.unpack('<Q', zh.read(8))[0]
            zh.seek(z64len, 1)
        elif data == b'PK\x06\x07':
            # zip64 end central directory locator
            zh.seek(16, 1)
        else:
            raise zipfile.BadZipFile("Invalid record signature '{}' at {}".format(data, recpos))

def isValidZipFile(zh):
    valid = True
    try:
        if not hasattr(zh, "read"):
            zh = open(zh, "rb")
        validateZipFile(zh)
    except zipfile.BadZipFile:
        valid = False
    return valid

def seekZipExtFile(self, offset, from_what = 0):
    """Seek method for ZipExtFile

    Allows repositioning within a zipfile. Does not perform actual reposition,
    but rather reads forward if the seek is ahead, or reads from zero if the
    seek is behind the current position."""
    curr_pos = self.tell()
    new_pos = offset # Default to seek from start
    if from_what == 1: # Seek from current offset
        new_pos = curr_pos + offset
    elif from_what == 2: # Seek from EOF
        new_pos = self._seeklen + offset

    if new_pos > self._seeklen:
        new_pos = self._seeklen

    if new_pos < 0:
        new_pos = 0

    read_offset = new_pos - curr_pos
    buff_offset = read_offset + self._offset

    if buff_offset >= 0 and buff_offset < len(self._readbuffer):
        # Just move the _offset index if the new position is in the _readbuffer
        self._offset = buff_offset
        read_offset = 0
    elif read_offset < 0:
        # Position is before the current position. Reset the ZipExtFile
        # object and read up to the new position.
        self._fileobj.seek(self._startcomp)
        self._running_crc = self._startcrc
        self._compress_left = self._complen
        self._left = self._seeklen
        self._readbuffer = b''
        self._offset = 0
        self._decompressor = zipfile._get_decompressor(self._compress_type)
        self._eof = False
        read_offset = new_pos

    # The read offset should be positive or zero.
    # Keep reading until the offset is zero
    while read_offset > 0:
        read_len = min(1024 * 1024, read_offset)
        self.read(read_len)
        read_offset -= read_len

    return self.tell()

def tellZipExtFile(self):
    offset = self._seeklen - self._left - len(self._readbuffer) + self._offset
    return offset

def makeseekable(zh):
    try:
        if zh.seekable():
            return zh
    except Exception:
        pass
    # Keep track of the start of compressed data in order to reset to that point
    zh._startcomp = zh._fileobj.tell()
    # This is usually zero, but no chances were taken
    zh._startcrc  = zh._running_crc
    # These two values need to be restored when the object is reset
    zh._complen   = zh._compress_left
    zh._seeklen   = zh._left
    # Yes, yes we are
    zh.seekable   = lambda: True
    zh.seek       = types.MethodType(seekZipExtFile, zh)
    zh.tell       = types.MethodType(tellZipExtFile, zh)
    return zh

def GatherFileData(f):
    crc32 = zlib.crc32(b'')
    filelen = 0
    f.seek(0)
    for i in f:
        crc32 = zlib.crc32(i, crc32)
        filelen += len(i)

    return filelen, "{:08x}".format(crc32)

def ParseZipToParent(root, zf):
    for zi in zf.infolist():
        attr = {"name": zi.filename}
        if not zi.filename.endswith('/'):
            with zf.open(zi) as zh:
                zh = makeseekable(zh)
                if isValidZipFile(zh):
                    ParseZipToParent(ET.SubElement(root, "zip", attr), zipfile.ZipFile(zh))
                else:
                    attr["crc32"] = "{:08x}".format(zi.CRC)
                    attr["file_size"] = str(zi.file_size)
                    attr["compress_size"] = str(zi.compress_size)
                    ET.SubElement(root, "file", attr)

def ParsePathToParent(root, srcpath):
    for entry in sorted(os.listdir(srcpath)):
        attr = {"name": entry}
        entrypath = os.path.join(srcpath, entry)
        print("\r{}".format(entrypath), end='', file=sys.stderr)
        if os.path.isdir(entrypath):
            ParsePathToParent(ET.SubElement(root, "dir", attr), entrypath)
        elif os.path.isfile(entrypath):
            if isValidZipFile(entrypath):
                ParseZipToParent(ET.SubElement(root, "zip", attr), zipfile.ZipFile(entrypath))
            else:
                filelen, crc32 = GatherFileData(open(entrypath, "rb"))
                attr["crc32"] = crc32
                attr["file_size"] = str(filelen)
                ET.SubElement(root, "file", attr)

def main():
    aparse = argparse.ArgumentParser(description='Create Romset DAT (RAT) file from directory')
    aparse.add_argument('-o', '--output', help='Output RAT to file <output>')
    aparse.add_argument('src', help='Source directory')

    args = aparse.parse_args()

    if not os.path.isdir(args.src):
        raise ValueError("Source '{}' not a directory".format(args.src))

    tree = ET.ElementTree(ET.Element("romset"))
    root = tree.getroot()

    ParsePathToParent(root, args.src)

    print("", file=sys.stderr)

    tree.write(sys.stdout, encoding="unicode", xml_declaration=True)

if __name__ == '__main__':
    main()
