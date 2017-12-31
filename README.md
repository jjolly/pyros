# pyros
Python scripts for managing romsets

You have found yet another romset manager, along the likes of ClrMamePro and Romvault. Like it's predecessors, the intention of Pyros is to create a complete set of machine rom files from other sets of incomplete files and a DATFile. The incomplete files can be either zipped files or unzipped files. At this time Pyros does not support the uncompression of 7zip files.

This python script requires Python v3.4 or later.

## Installation:

Copy the file into your ```<home>/bin``` directory, or anywhere your PATH reaches. There aren't complicated config files or libraries. Just make sure Python is installed and you're ready to go.

You may need to set the script file as executable, like this:
```chmod u+x ~/bin/pyros```

## Usage:
```./pyros <destination directory> <datfile> <source directory>...```

If I wanted to update a romset for my Fig&trade; Game Console, from version 2.55 to 2.56, and I had my files in the following directories:
* fig-2.55 - Directory containing the old set of Fig&trade; roms
* fig-update-2.55-to-2.56 - Directory containing the small subset of updated roms to add to the new set
* fig-2.56 - Directory that will contain my new Fig&trade; roms
* fig-2.56.dat - DATFile containing the romset definition for Fig&trade; 2.56

I would create my new romset with the following command:

```./pyros fig-2.56 fig-2.56.dat fig-2.55 fig-update-2.55-to-2.56```

As a personal example, because I use BTRFS for my romsets, and keep each set in a subvolume, I just do the following:

```
mv fig-2.55 fig-2.56
btrfs subvolume snapshot -r fig-2.56 fig-2.55
./pyros fig-2.56 fig-2.56.dat fig-2.55 fig-update-2.55-to-2.56
btrfs subvolume delete fig-2.55
```

This works well because Pyros will identify and skip romsets that are complete, and only update those files that need it.

## How it works:
It's really just a three step process:
* Compile a list of all the files in the source director(y/ies), recursively.
* Match files from the list to entries within the DATFile, making a list of machines, their roms, and where to find them
* Build the new torrentzipped romset

## What about pytor.py
That script was created to help clean the cruft out of my romsets. After building a romset, it's good to remove any obsoleted files.

## pytor.py usage
```./pytor <torrent file> <path to files in torrent>```

With the following:
* fig-2.56 - Directory of my Fig&trade; 2.56 romset - recently rebuilt
* fig-2.56.torrent - Torrent file for the Fig&trade; 2.56 romset

```
./pytor fig-2.56.torrent fig-2.56
```

You will see a list of files that do not belong to that torrent:
```
fig-2.56/kidgame.zip
fig-2.56/advgame.zip
fig-2.56/arcgame.zip
```

From the Linux command line, I use the script like this:
```
mkdir 2.55-rollback
for i in $(./pytor fig-2.56.torrent fig-2.56); do mv $i 2.55-rollback; done
```

And now I have a clean romset, and a set of files I can use if I need to return to an older romset version.

## Limitations:
As with any program, it can't do everything. Here are a few of the missing features and possible workarounds:

* Only builds merged sets
  * Split sets and non-merged sets will come as a later feature.
* Does not read 7zipped files
  * Will read unzipped files, so uncompress those 7zips.
* Works with only one datfile at a time
  * I get around this by running scripts that loop through a directory of dats.
* Does not work with mame -listxml
* Does not manage CHDs


## Acknowledgements
I'd like to thank:
* The Pleasuredome community. You folks are awesome
* ClrMamePro. You've done a great job keeping us going.
* Romvault. Thanks for the Linux support.
