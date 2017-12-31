#!/usr/bin/python

from __future__ import print_function
import sys
import os
import argparse
import hashlib

def bencode_readint(f, c):
    val = 0
    if c == None:
        c = f.read(1)
    while c.isdigit():
        val = val * 10 + int(c)
        c = f.read(1)
    return val, c

def bencode_read(f, etype):
    if etype == None:
        etype = f.read(1)
    if etype == 'd':
        data = {}
        c = f.read(1)
        while c != 'e':
            index = bencode_read(f, c)
            data[index] = bencode_read(f, None)
            c = f.read(1)
        return data
    elif etype == 'l':
        data = []
        c = f.read(1)
        while c != 'e':
            data.append(bencode_read(f, c))
            c = f.read(1)
        return data
    elif etype == 'i':
        val, c = bencode_readint(f, None)
        if c != 'e':
            raise ValueError
        return val
    elif etype.isdigit():
        slen, c = bencode_readint(f, etype)
        if c != ':':
            raise ValueError('Expected ":", got "' + c + '" at offset %i' % f.tell())
        return f.read(slen)
    else:
        raise ValueError

def list_unfound(path, intorr):
    for filename in os.listdir(path):
        filepath = os.path.join(path, filename)
        if os.path.isdir(filepath):
            list_unfound(filepath, intorr)
        elif filepath not in intorr:
            print(filepath)

def pieces_generator(srcpath, info):
    """Yield pieces from download file(s)."""
    piece_info = {'files': [], 'sha1': None}
    piece_length = info['piece length']
    if 'files' in info: # yield pieces from a multi-file torrent
        piece = ""
        for file_info in info['files']:
            flen = file_info['length']
            path = os.path.join(srcpath, *file_info['path'])
            try:
                sfile = open(path.decode('UTF-8'), "rb")
            except IOError:
                sfile = None
            while flen > 0:
                rlen = piece_length-len(piece)
                if rlen > flen:
                    rlen = flen
                piece_info['files'].append({'name': path, 'size read': rlen})
                flen -= rlen
                segment = ''
                if sfile:
                    segment = sfile.read(rlen)
                piece += segment + '\0' * (rlen - len(segment))
                if len(piece) == piece_length:
                    piece_info['sha1'] = hashlib.sha1(piece).digest()
                    yield piece_info
                    piece = ""
                    piece_info = {'files': [], 'sha1': None}
            if sfile:
                sfile.close()
        if piece != "":
            piece_info['sha1'] = hashlib.sha1(piece).digest()
            yield piece_info
    else: # yield pieces from a single file torrent
        flen = info['length']
        path = os.sep.join([srcpath] + [info['name']])
        try:
            sfile = open(path.decode('UTF-8'), "rb")
        except IOError:
            sfile = None
        while flen > 0:
            rlen = piece_length
            if rlen > flen:
                rlen = flen
            flen -= rlen
            segment = ''
            if sfile:
                segment = sfile.read(rlen)
            piece = segment + '\0' * (rlen - len(segment))
            yield {'files': [{'name': path, 'size read': rlen}], 'sha1': hashlib.sha1(piece).digest}
        if sfile:
            sfile.close()

def pytor_get_completion(path, info):
    complete = {}
    pieces = pieces_generator(path, info)
    i = 0
    for piece_info in pieces:
        for pfile in piece_info['files']:
            size_read = pfile['size read']
            if piece_info['sha1'] != info['pieces'][i*20:(i+1)*20]:
                size_read = 0
            if pfile['name'] in complete:
                complete[pfile['name']] += size_read
            else:
                complete[pfile['name']] = size_read
        i += 1
        print('%i of %i complete (%.1f%%)\r' % (i, len(info['pieces']) / 20, 2000.0 * i / len(info['pieces'])), file=sys.stderr, end='')
    print('', file=sys.stderr)
    return complete

def pytor_get_file_sizes(path, info):
    intorr = {}
    if 'files' not in info:
        intorr[os.path.join(path, info["name"])] = info['length']
    else:
        for tfile in info['files']:
            intorr[os.path.join(path, *tfile["path"])] = tfile['length']
    return intorr

if __name__ == "__main__":
    aparse = argparse.ArgumentParser(description="Torrent Manipulator")
    aparse.add_argument('-c', '--complete', help='Only show completed files', action='store_true')
    aparse.add_argument('-i', '--incomplete', help='Only show incomplete files', action='store_true')
    aparse.add_argument('-u', '--untracked', help='Only show untracked files', action='store_true')
    aparse.add_argument('-p', '--percent', help='Show percent complete for files', action='store_true')
    aparse.add_argument('-s', '--start', help='Show percent complete overall', action='store_true')
    aparse.add_argument('src', help='Torrent file to manipulate')
    aparse.add_argument('path', help='Path to files in torrent')

    args = aparse.parse_args()

    showall = True
    if args.complete or args.incomplete or args.untracked or args.start:
        showall = False

    f = open(args.src, 'rb')

    data = bencode_read(f, None)

    complete = {}
    if not args.untracked or showall or args.complete or args.incomplete or args.start:
        complete = pytor_get_completion(args.path, data['info'])

    intorr = pytor_get_file_sizes(args.path, data['info'])

    total = 0
    finished = 0

    for tfpath in intorr:
        size_total = intorr[tfpath]
        size_complete = 0
        if tfpath in complete:
            size_complete = complete[tfpath]
        total += size_total
        finished += size_complete
        if showall or (args.complete and size_total == size_complete) or (args.incomplete and size_total != size_complete):
            if showall or args.percent:
                print('[%5.1f%%] ' % (100.0 * size_complete / size_total), end='')
            print(tfpath)

    if showall or args.untracked:
        list_unfound(args.path, intorr)

    if showall or args.start:
        print('Completed %i of %i (%.1f%%)' % (finished, total, 100.0 * finished / total))

