#!/usr/bin/env python
# vim: noet

from subprocess import *
from pyinotify import *
import re, os, threading, signal, time

pargs = {
	"shell":  True,
	"stdin":  PIPE,
	"stdout": PIPE,
	"stderr": PIPE
}

class Gnokii:
	class SmsReader(threading.Thread):
		def __init__(self):
			threading.Thread.__init__(self)
			self.proc = None
			
		def run(self):
			# start gnokii, and block this thread until it's
			# finished (probably by termination via self.stop)
			self.proc = Popen(["gnokii --smsreader"], **pargs)
			self.proc.wait()
			
		def stop(self):
			# terminate the gnokii process, to exit
			# smsreader mode (after calling this, join
			# the thread to wait for this to complete)
			if not self.proc:
				return False
			
			try:
				os.kill(self.proc.pid, signal.SIGINT)
				os.waitpid(self.proc.pid, 0)
			
			# something went wrong?
			# i don't really care
			except OSError: pass 
	
	
	class SmsNotifier(ProcessEvent):
		def my_init(self, receiver):
			self.receiver = receiver
	
		def process_IN_CREATE(self, event):
			m = re.compile("^sms_(\d+)_").match(event.name)
			if m is not None:
		
				# read the contents of the text message
				# todo: perhaps delete the file
				f = open(event.path + "/" + event.name)
				message = f.read()
				f.close()
			
				# invoke the eventual receiver, providing
				# the senders number and the message
				self.receiver(m.group(1), message)
	
	
	def __init__(self, receiver=None):
		self.set_receiver(receiver)
		self.notifier = None
		self.reader = None
		self.quit = None
	
	
	# start watching for new sms messages
	def set_receiver(self, receiver):
		if receiver is not None:
			self.receiver = receiver
		
			# ensure that the sms receiving directory exists,
			# because gnokii may not have created it yet
			sms_dir = "/tmp/sms"
			if not os.path.isdir(sms_dir):
				os.mkdir(sms_dir)

			# start monitoring /tmp/sms for new messages
			# (in a separate thread), and send them all
			# to the receiver class/method. note that
			# THIS IS ALWAYS MONITORING, EVEN WHEN
			# GNOKII IS NOT IN SMSREADER MODE
			wm = WatchManager()
			self.notifier = ThreadedNotifier(
				wm, self.SmsNotifier(Stats(),
				receiver=self.receiver))
			wm.add_watch(sms_dir, IN_CREATE)
			self.notifier.setDaemon(True)
			self.notifier.start()
	
	
	def start_reader(self):
		if self.reader:
			# danger, will robinson!
			msg = "Gnokii.start_reader called " +\
			      "when reader was not None"
			raise(Warning, msg)
		
		# start a new gnokii in a new thread
		self.reader = self.SmsReader()
		self.reader.setDaemon(True)
		self.reader.start()
	
	
	def stop_reader(self):
		if self.reader:
			self.reader.stop()
			self.reader = None
	
	
	def run(self):      self.start_reader()
	def shutdown(self): self.stop_reader()
	
	
	def send(self, dest, msg):
		print "Sending to %s: %s"\
			% (dest, msg)
		
		# temporaily stop smsreader
		# (it blocks gnkii sending)
		self.stop_reader()
		
		# send the sms via a new gnokii process
		out, err = Popen(["gnokii --sendsms $0", dest], **pargs).communicate(msg)
		sent = (err.find("Send succeeded!") > 0)
		
		# create a new smsreader process,
		# and return the boolean status
		self.start_reader()
		return sent




gnokii = None

def SmsSender(username, password, server="localhost", port=13013):
	global gnokii
	if not gnokii:
		gnokii = Gnokii()
	return gnokii

def SmsReceiver(receiver):
	global gnokii
	if not gnokii: gnokii = Gnokii()
	gnokii.set_receiver(receiver)
	return gnokii




if __name__ == "__main__":
	
	def iGotAnSMS(caller, msg):
		print "%s says: %s" % (caller, msg)
		sent = g.send(caller, "Thanks for those %d characters!" % len(msg))
	
	# fire up gnokii to wait for
	# incomming messages
	g = Gnokii(iGotAnSMS)
	print "Waiting for SMS..."
	g.run()
	
	try:
		# block until ctrl+c
		while True: time.sleep(1)
		
	except KeyboardInterrupt:
		print "Shutting Down..."
		g.shutdown()

