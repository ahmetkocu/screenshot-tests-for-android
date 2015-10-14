#!/usr/bin/env python
#
# Copyright (c) 2014-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.
#

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import os
import sys
import tempfile
import subprocess
import xml.etree.ElementTree as ET
import getopt
import shutil
from . import metadata
from .simple_puller import SimplePuller
import zipfile
from . import aapt
from . import common

from os.path import join
from os.path import abspath

ROOT_SCREENSHOT_DIR = '/sdcard/screenshots'
OLD_ROOT_SCREENSHOT_DIR = '/data/data/'

def usage():
    print >>sys.stderr, "usage: ./scripts/screenshot_tests/pull_screenshots com.facebook.apk.name.tests [--generate-png]"
    return

def generate_html(dir):
    root = ET.parse(join(dir, 'metadata.xml')).getroot()
    alternate = False
    index_html = abspath(join(dir, "index.html"))
    with open(index_html, "w") as html:
        html.write('<!DOCTYPE html>')
        html.write('<html>')
        html.write('<head>')
        html.write('<script src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js"></script>')
        html.write('<script src="https://ajax.googleapis.com/ajax/libs/jqueryui/1.11.3/jquery-ui.min.js"></script>')
        html.write('<script src="default.js"></script>')
        html.write('<link rel="stylesheet" href="https://ajax.googleapis.com/ajax/libs/jqueryui/1.11.3/themes/smoothness/jquery-ui.css" />')
        html.write('<link rel="stylesheet" href="default.css"></head>')
        html.write('<body>')

        html.write('<!-- begin results -->')
        for screenshot in root.iter('screenshot'):
            alternate = not alternate
            html.write('<div class="screenshot %s">' % ('alternate' if alternate else ''))
            html.write('<div class="screenshot_name">%s</div>' % (screenshot.find('name').text))
            html.write('<button class="view_dump" data-name="%s">Dump view hierarchy</button>' % (screenshot.find('name').text))

            extras = screenshot.find('extras')
            if extras is not None:
                str = ""
                for node in extras:
                    if node.text is not None:
                        str = str + "*****" + node.tag + "*****\n\n" + node.text + "\n\n\n"
                if str != "":
                    extra_html = '<button class="extra" data="%s">Extra info</button>' % str
                    html.write(extra_html.encode('utf-8').strip())

            description = screenshot.find('description')
            if description is not None:
                html.write('<div class="screenshot_description">%s</div>' % description.text)

            error = screenshot.find('error')
            if error is not None:
                html.write('<div class="screenshot_error">%s</div>' % error.text)
            else:
                write_image(dir, html, screenshot)

            html.write('</div>')

        html.write('</body></html>')
        return index_html

def write_image(dir, html, screenshot):
    html.write('<table class="img-wrapper">')
    for y in xrange(int(screenshot.find('tile_height').text)):
        html.write('<tr>')
        for x in xrange(int(screenshot.find('tile_width').text)):
            html.write('<td>')
            image_file = "./" + common.get_image_file_name(screenshot.find('name').text, x, y)

            if os.path.exists(join(dir, image_file)):
                html.write('<img src="%s" />' % image_file)

            html.write('</td>')
        html.write('</tr>')
    html.write('</table>')


def test_for_wkhtmltoimage():
    if subprocess.call(['which', 'wkhtmltoimage']) != 0:
        raise RuntimeError("""Could not find wkhtmltoimage in your path, we need this for generating pngs
Download an appropriate version from:
    http://wkhtmltopdf.org/downloads.html""")

def generate_png(path_to_html, path_to_png):
    test_for_wkhtmltoimage()
    subprocess.check_call(['wkhtmltoimage', path_to_html, path_to_png], stdout=sys.stdout)


def copy_assets(destination):
    """Copy static assets required for rendering the HTML"""
    _copy_asset("default.css", destination)
    _copy_asset("default.js", destination)
    _copy_asset("background.png", destination)

def _copy_asset(filename, destination):
    thisdir = os.path.dirname(__file__)
    _copy_file(abspath(join(thisdir, filename)), join(destination, filename))

def _copy_file(src, dest):
    if os.path.exists(src):
        shutil.copyfile(src, dest)
    else:
        _copy_via_zip(src, None, dest)

def _copy_via_zip(src_zip, zip_path, dest):
    if os.path.exists(src_zip):
        zip = zipfile.ZipFile(src_zip)
        input = zip.open(zip_path, 'r')
        with open(dest, 'w') as output:
            output.write(input.read())
    else:
        # walk up the tree
        head, tail = os.path.split(src_zip)

        _copy_via_zip(head, tail if not zip_path else (tail + "/" + zip_path), dest)

def pull_metadata(package, dir, adb_puller):
    metadata_file = '%s/%s/screenshots-default/metadata.xml' % (ROOT_SCREENSHOT_DIR, package)
    old_metadata_file = '%s/%s/app_screenshots-default/metadata.xml' % (OLD_ROOT_SCREENSHOT_DIR, package)

    if adb_puller.remote_file_exists(metadata_file):
        adb_puller.pull(metadata_file, join(dir, 'metadata.xml'))
    elif adb_puller.remote_file_exists(old_metadata_file):
        adb_puller.pull(old_metadata_file, join(dir, 'metadata.xml'))
    else:
        create_empty_metadata_file(dir)

def create_empty_metadata_file(dir):
    with open(join(dir, 'metadata.xml'), 'w') as out:
        out.write("""<?xml version="1.0" encoding="UTF-8"?>
<screenshots>
</screenshots>""")

def pull_images(dir, adb_puller):
    root = ET.parse(join(dir, 'metadata.xml')).getroot()
    for s in root.iter('screenshot'):
        filename_nodes = s.findall('absolute_file_name')
        for filename_node in filename_nodes:
            adb_puller.pull(filename_node.text, join(dir, os.path.basename(filename_node.text)))
        dump_node = s.find('view_hierarchy')
        if dump_node is not None:
            adb_puller.pull(dump_node.text, join(dir, os.path.basename(dump_node.text)))

def pull_all(package, dir, adb_puller):
    pull_metadata(package, dir, adb_puller=adb_puller)
    pull_images(dir, adb_puller=adb_puller)

def pull_filtered(package, dir, adb_puller, filter_name_regex=None):
    pull_metadata(package, dir, adb_puller=adb_puller)
    metadata.filter_screenshots(join(dir, 'metadata.xml'), name_regex=filter_name_regex)
    pull_images(dir, adb_puller=adb_puller)

def _summary(dir):
    root = ET.parse(join(dir, 'metadata.xml')).getroot()
    count = len(root.findall('screenshot'))
    print("Found %d screenshots" % count)

def pull_screenshots(process,
                     adb_puller,
                     temp_dir=None,
                     filter_name_regex=None,
                     record=None,
                     verify=None,
                     opt_generate_png=None):
    temp_dir = temp_dir or tempfile.mkdtemp(prefix='screenshots')
    copy_assets(temp_dir)

    pull_filtered(process, adb_puller=adb_puller, dir=temp_dir, filter_name_regex=filter_name_regex)
    path_to_html = generate_html(temp_dir)

    if record or verify:
        # don't import this early, since we need PIL to import this
        from .recorder import Recorder
        recorder = Recorder(temp_dir, record or verify)
        if verify:
            recorder.verify()
        else:
            recorder.record()

    if opt_generate_png:
        generate_png(path_to_html, opt_generate_png)
        shutil.rmtree(temp_dir)
    else:
        print("\n\n")
        _summary(temp_dir)
        print('Open the following url in a browser to view the results: ')
        print('  file://%s' % path_to_html)
        print("\n\n")

def setup_paths():
    android_home = common.get_android_sdk()
    os.environ['PATH'] = os.environ['PATH'] + ":" + android_home + "/platform-tools/"

def main(argv):
    try:
        opt_list, rest_args = getopt.gnu_getopt(
            argv[1:],
            "eds:",
            ["generate-png=", "filter-name-regex=", "apk", "record=", "verify="])
    except getopt.GetoptError, err:
        usage()
        return 2

    if len(rest_args) != 1:
        usage()
        return 2

    process = rest_args[0]  # something like com.facebook.places.tests

    opts = dict(opt_list)

    if "--apk" in opts:
        # treat process as an apk instead
        process = aapt.get_package(process)

    puller_args = []
    if "-e" in opts:
        puller_args.append("-e")

    if "-d" in opts:
        puller_args.append("-d")

    if "-s" in opts:
        puller_args += ["-s", opts["-s"]]

    return pull_screenshots(process,
                            filter_name_regex=opts.get('--filter-name-regex'),
                            opt_generate_png=opts.get('--generate-png'),
                            record=opts.get('--record'),
                            verify=opts.get('--verify'),
                            adb_puller=SimplePuller(puller_args))

if __name__ == '__main__':
    sys.exit(main(sys.argv))
