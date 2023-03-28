#!/usr/bin/env python

import re
import os
import gzip
import datetime


def read_file(res):
    run_dates = []

    if res.endswith(".gz"):
        func = gzip.open(res, 'rt')
    else:
        func = open(res, 'r')

    with func as fp:
        runtime = 0
        lines = fp.readlines()
        for line in lines:
            if 'NIZPODOH' in line:
                date_point = line.split(' - ')[0]
                date_point = datetime.datetime.strptime(date_point, '%Y-%m-%d %H:%M:%S,%f')
                run_dates.append(date_point)
            if (len(run_dates) > 0 and line == line[-1]) or (len(run_dates) > 0 and 'NIZPODOH' not in line):
                diff = run_dates[-1] - run_dates[0]
                seconds = diff.seconds
                runtime += seconds
                run_dates = []
        run_date = re.sub('[^\d]', '', file)
        if not run_date:
            run_date = datetime.datetime.fromtimestamp(os.path.getmtime(res)).strftime('%Y-%m-%d')
        else:
            run_date = datetime.datetime.strptime(run_date,'%Y%m%d').strftime('%Y-%m-%d')
        dates[run_date] = round(runtime/3600, 2)


if __name__ == '__main__':
    dates = {}
    base_url = '/var/www/biganto.com/logs/'
    for file in os.listdir(base_url):
        if 'builder.log' in file:
            read_file(base_url + file)

    log_url = '/home/biganto/np_runtime.log'
    if not os.path.exists(log_url):
        open(log_url, 'w').close()

    with open(log_url, "r") as fp:
        lines = fp.readlines()

    with open(log_url, "a") as fp:
        for k, v in sorted(dates.items()):
            for line in lines:
                if k in line:
                    break
            else:
                fp.write(k + '\t' + str(v) + '\n')

            print(k, '\t', v)

