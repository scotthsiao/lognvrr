from threading import Timer
from time import sleep
import subprocess
import time
import datetime
import re
import signal
import os

timeout = 10
prefix = "capture"
mp4_filename = prefix + ".mp4"
log_filename = prefix + ".log"
vtt_filename = prefix + ".vtt"
device_serial = "LGE988f492768"

lines = []
log_bits = []

ctrl_c = 0
times_up = 0

def stop_logging():	
	global times_up
	print "timeout (%d) is expired" % timeout
	times_up = 1

def get_time():
	global dt_begin
	ts_ori = subprocess.check_output(["adb", "-s", device_serial, "shell" ,"echo" ,"$EPOCHREALTIME"])
	ts_float = float(ts_ori)
	dt_begin = datetime.datetime.fromtimestamp(ts_float)

def signal_handler(signal, frame):
	global ctrl_c
	print " Ctrl+C detected"
	ctrl_c = 1

def get_mp4_length():
	str_length = subprocess.check_output("ffmpeg -i " + mp4_filename + " 2>&1 | grep Duration | cut -d ' ' -f 4 | sed s/,//", shell=True).rstrip()
	if str_length == '':
		print "get_mp4_length: bad mp4 file"
		return "00:00:00.000"
	dt_var = datetime.datetime.strptime(str_length, "%H:%M:%S.%f")
	delta = datetime.timedelta(seconds = 1)
	t_var = dt_var.time()
	# t_mod = (datetime.datetime.combine(datetime.date(1,1,1),t_var) + delta).time()
	dt_mod = datetime.datetime.combine(datetime.date(1,1,1),t_var) + delta
	str_timemod = '{:02d}:{:02d}:{:02d}.{:03d}'.format(dt_mod.hour, dt_mod.minute, dt_mod.second, dt_mod.microsecond / 1000)	
	print "Recorded time length is " + str_timemod
	return str_timemod

def get_vtt_timestamp(dt1, dt2):
	td_elapse = dt2 - dt1
	hours, minutes = divmod(td_elapse.total_seconds(), 3600)
	minutes, seconds = divmod(minutes, 60)
	seconds, microseconds = divmod(seconds, 1)
	microseconds = microseconds * 1000
	str_timediff = '{:02.0f}:{:02.0f}:{:02.0f}.{:03.0f}'.format(hours, minutes, seconds, microseconds)
	return str_timediff

def vtt_keyword_converter(ori_str):
	censored_str = re.sub(r'-->', '->', ori_str)
	censored_str = re.sub(r'\t', '    ', censored_str)
	censored_str = re.sub(r'"', '\'', censored_str)	
	return censored_str

def parse_adb_logs():
	global lines
	global log_bits
	global dt_begin

	i = 0

	for line in lines:
		m = re.search('(\d+-\d+) (\d+:\d+:\d+\.\d+) ([VDIWEFS])/([A-Za-z =>:\._\[\]\-0-9]+)\(([\d ]+)\): (.+)', line)
		if m:
			date_all = '{:d}-{:s} {:s}'.format(dt_begin.year, m.group(1), m.group(2))
			dt_temp = datetime.datetime.strptime(date_all, '%Y-%m-%d %H:%M:%S.%f')
			log_bits.append([i, get_vtt_timestamp(dt_begin, dt_temp), m.group(1), m.group(2), m.group(3), m.group(4).strip(), m.group(5).strip(), m.group(6)])
			i += 1
		else:
			m = re.search('^--------- beginning of', line)
			if m:
				print "[RE] skip seperator line"
			else:
				if line:
					print "[RE] failed. raw dump:"
					print line
					str_dump = ':'.join(x.encode('hex') for x in line)
					print str_dump
		

def export_vtt_file():
	global log_bits
	global dt_begin
	global dt_end

	checkpoints = []
	for entry in log_bits:
		timestamp = entry[1]
		if timestamp in checkpoints:
			continue
		checkpoints.append(timestamp)

	checkpoints.append(get_vtt_timestamp(dt_begin, dt_end))

	last_mark = ""
	last_prior = ""
	f = open(vtt_filename, "w")
	f.write('WEBVTT')

	for entry in log_bits:

		cur_mark = entry[1]
		cur_prior = entry[4]
		next_mark = checkpoints[checkpoints.index(cur_mark)+1]

		m = re.search ('[VDIWEFS]', cur_prior) and (last_mark != cur_mark or last_prior != cur_prior)
		if m:
			key = "yes"
		else:
			key = "no"

		cue =  '\n\n{:d}\n'.format(entry[0])
		cue += '{:s} --> {:s}\n'.format(cur_mark, next_mark)
		cue += '{\n'
		cue += '"date": 	"{:s}",\n'.format(entry[2])
		cue += '"time": 	"{:s}",\n'.format(entry[3])
		cue += '"priority": "{:s}",\n'.format(entry[4])
		cue += '"process": 	"{:s}",\n'.format(entry[5])
		cue += '"PID": 		"{:s}",\n'.format(entry[6])
		cue += '"message": 	"{:s}",\n'.format(vtt_keyword_converter(entry[7].rstrip()))
		cue += '"key": 		"{:s}"\n'.format(key)	
		cue += '}'
		f.write(cue)
		last_mark = cur_mark
		last_prior = cur_prior
	f.close()

def cleanup_process():
	global proc_log
	global proc_recorder
	proc_log.send_signal(signal.SIGINT)
	proc_recorder.send_signal(signal.SIGINT)
	proc_log.wait()
	proc_recorder.wait()

def dump_array(array):
	for entry in array:
		print entry

def export_log_file():
	global lines
	f = open(log_filename, "w")
	for line in lines:
		f.write(line.rstrip()+"\n")
	f.close()		

signal.signal(signal.SIGINT, signal_handler)

t = Timer(timeout, stop_logging)

print "Using device serial: " + device_serial
print "Max recoding time limit: " + str(timeout) + " seconds. Press CTRL+C to finish logging."
t.start()

dt_begin = datetime.datetime.now()

subprocess.call('adb -s ' + device_serial + ' shell dumpsys power | grep "mScreenOn=true" | xargs -0 test -z && adb -s ' + device_serial + ' shell input keyevent 26', shell=True)
get_time()
subprocess.call(["adb", "-s", device_serial, "logcat", "-c"])

proc_log = subprocess.Popen("exec adb -s " + device_serial + " logcat -v time", shell=True, stdout=subprocess.PIPE, \
							stderr=subprocess.PIPE, preexec_fn=os.setpgrp)
proc_recorder = subprocess.Popen("exec adb -s " + device_serial + " shell screenrecord /sdcard/" + mp4_filename, shell=True, stdout=subprocess.PIPE, \
  							stderr=subprocess.PIPE, preexec_fn=os.setpgrp)

while True:
	if ctrl_c != 0 or times_up !=0:
		cleanup_process()
		dt_end = datetime.datetime.now()
		break
	else:
		time.sleep(0.5)

msg_stdout, msg_stderr = proc_log.communicate()
t.cancel()

sleep(1)
subprocess.call("adb -s " + device_serial + " pull /sdcard/" + mp4_filename, shell=True)
get_mp4_length()

lines = msg_stdout.split('\n')
parse_adb_logs()
export_vtt_file()
export_log_file()

