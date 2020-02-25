#!/usr/bin/env python3


import argparse
import configparser
import datetime
import re
import subprocess
import sys


scan_p = re.compile(b'^ *scan: *(.*) *$', re.MULTILINE)
scan_results_p = re.compile(b'scrub repaired [^ ]+ in ([0-9]+) days ([0-9]+):([0-9]+):([0-9]+) with [0-9]+ errors on (.+)$')


def main ():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true', default=None)
    parser.add_argument('pools', nargs='*')

    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read('autoscrub.ini')

    pools = args.pools if args.pools else config.sections()
    for pool in pools:
        if pool not in config:
            raise ConfigError(pool)

    for pool in pools:
        if args.force or time_to_scrub(config[pool]['ref'].lower(), pool):
            zpool_scrub(pool)


def handle_exception (func):
    try:
        func()
    except AutoscrubException as ex:
        print('{0}: {1}'.format(ex.prefix, ex), file=sys.stderr)
        sys.exit(ex.retcode)


def time_to_scrub (ref, pool):
    try:
        scan_time, end = zpool_status(pool)
    except NotScanned:
        return True

    start = end - scan_time

    if ref == 'start':
        period_start = start
    elif ref == 'end':
        period_start = end
    else:
        raise ConfigError('unknown value: {0}: ref: {1}'.format(pool, config[pool]['ref']))

    scrub_expected = period_start + datetime.timedelta(days=int(config[pool]['days']))
    return scrub_expected <= datetime.datetime.now()


def zpool_scrub (pool):
    args = ['zpool', 'scrub', pool]
    scrub_p = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = scrub_p.communicate()
    if stderr:
        raise ZFSCommandError(stderr.decode().strip())


def zpool_status (pool):
    args = ['zpool', 'status', pool]
    status_p = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = status_p.communicate()
    if stderr:
        raise ZFSCommandError(stderr.decode().strip())
    scan_p_match = scan_p.search(stdout)
    if not scan_p_match:
        raise NotScanned('{0}: absent'.format(pool))
    scan_results = scan_p_match.group(1)
    if scan_results == b'none requested':
        raise NotScanned('{0}: {1}'.format(pool, scan_results))
    scan_results_match = scan_results_p.match(scan_results)
    if not scan_results_match:
        raise ParseError('{0}: {1}'.format(pool, scan_results))
    days, hours, minutes, seconds, end = scan_results_match.groups()
    scan_td = datetime.timedelta(
        days = int(days),
        seconds = (
            (int(hours) * 60 * 60)
            + (int(minutes) * 60)
            + int(seconds)),
    )
    end_dt = datetime.datetime.strptime(end.decode(), '%a %b %d %H:%M:%S %Y')
    return (scan_td, end_dt)


class AutoscrubException (Exception):
    prefix = 'unknown'
    retcode = -1

class AutoscrubError (AutoscrubException):
    prefix = 'error'
    retcode = -2

class NotScanned (AutoscrubException): pass

class ConfigError (AutoscrubException):
    retcode = 1

class ZFSCommandError (AutoscrubError):
    retcode = 2

class ParseError (AutoscrubError):
    retcode = 3


if __name__ == '__main__':
    handle_exception(main)
