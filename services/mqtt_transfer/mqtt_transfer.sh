#!/bin/bash

SCRIPT=$(realpath "$0")
SCRIPTPATH=$(dirname "$SCRIPT")
MQTT_RELAY=$(dirname `dirname "$SCRIPTPATH"`)

reading_arg=0

while [ "$1" != "" ]; do
	if [ $reading_arg -eq 0 ]; then
		case "$1" in
			"-v")
				reading_arg=1 
				;;
			"-l")
				reading_arg=2
				;;
			*)
				echo "Unknown param $1"
				exit
				;;
		esac
	else
		case $reading_arg in
			1)
				venv_path=$1
				reading_arg=0
				;;
			2)
				logging_dir=$1
				reading_arg=0
				;;
		esac
	fi
	shift 1
done 

LOG_ARG=""
if [ ! -z ${logging_dir+x} ]; then
	LOG_ARG="--logging-dir $logging_dir"
fi

if [ ! -z ${venv_path+x} ]; then
	source "$venv_path"
fi

cd $MQTT_RELAY
echo "executing cmd: python "$SCRIPTPATH/mqtt_transfer.py" --root-dir "$MQTT_RELAY" $LOG_ARG"
python "$SCRIPTPATH/mqtt_transfer.py" --root-dir "$MQTT_RELAY" $LOG_ARG