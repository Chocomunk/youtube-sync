import youtube_dl
import argparse
import json
import copy
import glob
import sys
import re
import os


_version = 'youtube-sync v1.0'

ytdl_default_opts = {
    "extractaudio": True,
    "audioformat": 'm4a',
    "format": 'm4a',
    "nocheckcertificate": True,
    "ignoreerrors": True,
    "no_warnings": True,
    "noplaylist": True,
    "outtmpl": "./%(playlist_title)s/%(title)s.%(ext)s"
}


class NoPlaylistLink(Exception):
    pass


class NotYoutubePlaylist(Exception):
    pass


def load_json(filename, default_val=None):
    if not os.path.isfile(filename):
        return default_val
    else:
        with open(filename, 'r') as f:
            return json.load(f)


def write_json(filename, data, pretty=True):
    with open(filename, 'w') as f:
        if pretty:
            json.dump(data, f, indent=4)
        else:
            json.dump(data, f)


class ArchiveCheckLogger(object):

    def __init__(self, pop_list, quiet=False):
        self.songs = pop_list
        self.quiet = quiet

    def debug(self, msg):
        match = re.match(r'\[download\] (?P<title>.*) has already been recorded in archive', msg)
        if not self.quiet:
            print("<DEBUG> "+msg)
        if match:
            title = match.group('title')
            self.songs.pop(title, None)

    def warning(self, msg):
        print("<WARNING> "+msg)

    def error(self, msg):
        print("<ERROR> "+msg)


class YoutubeSync(object):

    def __init__(self):
        self.config_dir = os.path.join(os.getcwd(), '.sync')
        self.valid_dir = os.path.isdir(self.config_dir)

        self.sync_file = os.path.join(self.config_dir, "sync_archive.json")
        self.archive_file = os.path.join(self.config_dir, "archive.txt")
        self.config_file = os.path.join(self.config_dir, "sync_config.conf")
        self.ytdl_opts_file = os.path.join(self.config_dir, "ytdl_opts.conf")

        self.sync_config = load_json(self.config_file, {})
        self.ytdl_opts = load_json(self.ytdl_opts_file, ytdl_default_opts)
        self.sync_archive = load_json(self.sync_file, {})

        quiet = self.ytdl_opts.get('quiet', None)
        if quiet is not None:
            self.ytdl_opts.pop('quiet')
        quiet = self.sync_config.get('quiet', False if quiet is None else quiet)
        self.remove_list = copy.copy(self.sync_archive)
        self.check_logger = ArchiveCheckLogger(self.remove_list, quiet=quiet)

    def init(self, playlist_link):
        valid_folder = True
        self.sync_config['playlist_link'] = playlist_link

        if not self.valid_dir:
            print("Creating youtube-sync folder...")
            os.makedirs(self.config_dir)
            valid_folder = False

        if not os.path.isfile(self.config_file):
            print("Creating youtube-sync config file")
            write_json(self.config_file, self.sync_config)

        if not os.path.isfile(self.ytdl_opts_file):
            print("Creating youtube-dl config file")
            write_json(self.ytdl_opts_file, self.ytdl_opts)

        if not valid_folder:
            print("Successfully initialized youtube-sync")
            print("Run 'youtube-sync --sync' to sync this folder")

    def sync(self):
        if not self.valid_dir:
            print("Cannot sync to an invalid dir")
            print("Try running 'youtube-sync --init'")
            return

        if not self.sync_config.get('playlist_link', None):
            raise NoPlaylistLink()

        self.ytdl_opts["download_archive"] = self.archive_file
        self.ytdl_opts["logger"] = self.check_logger

        with youtube_dl.YoutubeDL(self.ytdl_opts) as ytdl:
            meta = ytdl.extract_info(self.sync_config.get('playlist_link'), download=True)
        if meta.get('_type') is not 'playlist' and meta.get("extractor_key") is not 'YoutubePlaylist':
            raise NotYoutubePlaylist
        for entry in meta.get("entries"):
            self.sync_archive[entry['title']] = entry['id']
        self._update_files(meta['title'])

    def _update_files(self, playlist_title):
        rm_ids = list(self.remove_list.values())
        rm_titles = list(self.remove_list.keys())
        removed_songs = []
        with open(self.archive_file, 'r+') as file:
            lines = file.readlines()
            file.seek(0)
            for line in lines:
                song_id = line.split()[1]
                if song_id in rm_ids:
                    title = rm_titles[rm_ids.index(song_id)]
                    removed_songs.append(title)
                    print("Removing song: {}".format(title))
                else:
                    file.write(line)
            file.truncate()

        for key in removed_songs:
            self.sync_archive.pop(key, None)
            path = self.ytdl_opts['outtmpl'] % {'playlist_title': playlist_title,
                                                'title': key,
                                                'ext': '*'}
            os.remove(glob.glob(path)[0])

        write_json(self.sync_file, self.sync_archive, pretty=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="A small module to sync a folder with a youtube playlist")
    parser.add_argument('-i', '--init', action="store", dest="playlist_link", type=str, default=None,
                        help="Initializes folder as a youtube-sync folder")
    parser.add_argument('-p', '--path', action="store", dest="ytsc_path", type=str, default=None,
                        help="Specifies different youtube-sync directory")
    parser.add_argument('-s', '--sync', action="store_true", default=False,
                        help="Sync youtube-sync directory with the assigned youtube playlist")
    parser.add_argument('-v', '--version', action='version', version=_version)
    args = parser.parse_args()

    orig_dir = os.getcwd()
    if args.ytsc_path is not None:
        os.chdir(args.ytsc_path)

    ytsc = YoutubeSync()
    if args.playlist_link is not None:
        ytsc.init(args.playlist_link)
    if args.sync:
        ytsc.sync()

    if args.ytsc_path is not None:
        os.chdir(orig_dir)

    if not len(sys.argv) > 1:
        print(parser.parse_args(['-h']))
