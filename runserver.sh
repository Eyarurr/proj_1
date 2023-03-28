#!/bin/sh

rq worker default quick &
./joint_server.py &

export FLASK_APP=visual
export FLASK_ENV=development
flask run

kill %1
kill %2
