#!/usr/bin/python

import os
import argparse

def bencode_readint(f):
    val = 0
    c = f.read(1)
    while c.isdigit():
        val = val * 10 + int(c)
        c = f.read(1)
    return val, c

def bencode_read(f):
    etype = f.read(1)
    if etype == 'd':
        data = {}
        while f.read(1) != 'e':
            f.seek(-1, os.SEEK_CUR)
            index = bencode_read(f)
            data[index] = bencode_read(f)
        return data
    elif etype == 'l':
        data = []
        while f.read(1) != 'e':
            f.seek(-1, os.SEEK_CUR)
            data.append(bencode_read(f))
        return data
    elif etype == 'i':
        val, c = bencode_readint(f)
        if c != 'e':
            raise ValueError
    elif etype.isdigit():
        f.seek(-1, os.SEEK_CUR)
        slen, c = bencode_readint(f)
        if c != ':':
            raise ValueError
        return f.read(slen)
    else:
        raise ValueError

def list_unfound(path, intorr):
    for filename in os.listdir(path):
        filepath = os.path.join(path, filename)
        if os.path.isdir(filepath):
            list_unfound(filepath, intorr)
        elif filepath not in intorr:
            print filepath

if __name__ == "__main__":
    aparse = argparse.ArgumentParser(description="Torrent Manipulator")
    aparse.add_argument('src', help='Torrent file to manipulate')
    aparse.add_argument('path', help='Path to files in torrent')

    args = aparse.parse_args()

    f = open(args.src, 'rb')

    data = bencode_read(f)

    intorr = []

    if "files" not in data["info"]:
        intorr = [ data["info"]["name"] ]
    else:
        intorr = [os.path.join(args.path, *tfile["path"]) for tfile in data["info"]["files"]]

    list_unfound(args.path, intorr)

