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
	
	
	class _SmsNotifier(ProcessEvent):
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
	
	
	class SmsNotifier(_SmsNotifier):
		def my_init(self, receiver):
			self.receiver = receiver
		
	
	class OldSmsNotifier(_SmsNotifier):
		def __init__(self, receiver):
			self.receiver = receiver
	
	
	def __init__(self, receiver=None):
		self.set_receiver(receiver)
		self.notifier = None
		self.reader = None
		self.quit = None
		self.buffer = []
	
	
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
			try:
				self.notifier = ThreadedNotifier(
					wm, self.SmsNotifier(Stats(),
					receiver=self.receiver))
				wm.add_watch(sms_dir, IN_CREATE)
			# this will fail with a NameError if we are using an
			# older version (< 0.8) of pyinotify, so we catch it and use
			# the class for backwards compatibility
			except NameError:
				self.notifier = ThreadedNotifier(
					wm, self.OldSmsNotifier(receiver=self.receiver))
				wm.add_watch(sms_dir, EventsCodes.IN_CREATE)
			self.notifier.setDaemon(True)
			self.notifier.start()
	
	
	def start_reader(self):
		if self.reader:
			# danger, will robinson!
			msg = "Gnokii.start_reader called " +\
			      "when reader was not None"
			print msg
			raise(Warning)
		
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
	
	
	def send(self, dest, msg, buffer=False):
		if buffer:
			self.buffer.append((dest, msg))
			return True
			
		# if the reader is currently running,
		# then stop it, send, and re-start it
		elif self.reader != None:
			self.stop_reader()
			r = self._send(dest, msg)
			self.start_reader()
			return r
			
		# if no reader is running, then
		# sending is really simple...
		else: return self._send(dest, msg)
	
	# 
	def _send(self, dest, msg):
		out, err = Popen(["gnokii --sendsms $0", dest], **pargs).communicate(msg)
		sent = (err.find("Send succeeded!") > 0)
		time.sleep(0.5)
	

	def flush(self):
		print "Flushing %d messages" % (len(self.buffer))
		self.stop_reader()
		
		# send each message in
		# order of receipt
		for tuple in self.buffer:
			dest, msg = tuple
			self._send(dest, msg)
		
		self.start_reader()
		self.buffer = []




gnokii = None

# args are inherited from pykannel, but aren't needed for gnokii
def SmsSender(username=None, password=None, server="localhost", port=13013):
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
	
	dest = raw_input("Please enter a phone number to receive SMS: ").strip()
	sender = SmsSender()
	if sender.send(dest, "Hello world! -pygnokii"):
		print "Message sent"
	
	def iGotAnSMS(caller, msg):
		print "%s says: %s" % (caller, msg)
		sent = sender.send(caller, "Thanks for those %d characters!" % len(msg))
	
	# fire up gnokii to wait
	# for incomming messages
	print "Waiting for incoming SMS..."
	receiver = SmsReceiver(iGotAnSMS)
	receiver.run()
	
	try:
		# block until interrupt
		while True:
			time.sleep(1)
	
	except KeyboardInterrupt:
		print "Shutting Down..."
		receiver.shutdown()

