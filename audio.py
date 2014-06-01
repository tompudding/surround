import jack
import time
import numpy
import wave
import struct
import glob
import os
import random

class JackClient(object):
    name = 'Pathfinder_Ambient'
    ac3name = 'ac3jack_1'
    def __init__(self):
        self.client = jack.Client(self.name)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self,type, value, traceback):
        self.close()
        return False

    def open(self):

        #make the ports
        self.ports = ['left',
                      'center',
                      'right',
                      'left_surround',
                      'right_surround',
                      'sub']
        self.targets = ['1_Left',
                        '2_Center',
                        '3_Right',
                        '4_LeftSurround',
                        '5_RightSurround',
                        '6_LFE']
        self.targets = [self.ac3name + ':' + name for name in self.targets]
        for port,target in zip(self.ports,self.targets):
            self.client.register_port(port, jack.IsOutput)

        self.client.activate()
        for port,target in zip(self.ports,self.targets):
            name = '%s:%s' % (self.name,port)
            print name,target
            self.client.connect(name,target)
        

        self.sample_rate = self.client.get_sample_rate()
        self.buffer_size = self.client.get_buffer_size()
        print self.buffer_size
        sec = 18.0
        self.pos = 0
        
        self.input_buffer = numpy.zeros((1,self.buffer_size), 'f')
        self.output_buffer = numpy.ones((6,self.buffer_size), 'f')
        x = numpy.sin( 2*numpy.pi*4400.0 * (numpy.arange(0,sec*6,1.0/(self.sample_rate),'f')[0:int(self.sample_rate*sec)*6]))
        print len(x),int(self.sample_rate*sec)
        self.output = numpy.reshape( x,
                                     (6, int(self.sample_rate*sec)) ).astype('f')
        #for i in xrange(6):
        #    for j in xrange(self.buffer_size):
        #        self.output_buffer[i][j] = 0.5

    def play(self,output):
        while True:
            try:
                self.client.process(output,self.input_buffer)
            except jack.OutputSyncError:
                continue
            break

    def close(self):
        self.client.deactivate()

class Sound(object):
    def __init__(self,filename):
        self.wave = wave.open(filename)
        if self.wave.getsampwidth() != 2:
            raise TypeError('Expected 2byte wav, got %d byte' % self.wave.getsampwidth())
        if self.wave.getnchannels() != 1:
            raise TypeError('Expected mono sound')
        
        self.samples = numpy.array([(float(struct.unpack('<h',self.wave.readframes(1))[0])/0x8000) for i in xrange(self.wave.getnframes())])

        freq = self.wave.getframerate()
        if freq == 44100:
            pass
        elif freq == 22050:
            self.samples = numpy.repeat(self.samples,2)
        else:
            raise ValueError('Unsupported frequency %d' % freq)
        
class Seaside(object):
    def __init__(self,path):
        self.sounds = []
        self.client = None
        for filename in glob.glob(os.path.join(path,'*.wav')):
            sound = Sound(filename)
            if os.path.basename(filename) == 'background.wav':
                self.background = sound
            else:
                self.sounds.append(sound)
        timeline = []
        pos = 0
        while pos < 20000:
            next_event = pos + random.expovariate(1/(3000.0))
            timeline.append((next_event,random.choice(self.sounds)))
            pos = next_event
        self.start = None
        self.audio_buffer = numpy.tile(self.background.samples, (6,1)).astype('f')
        self.pos = 0

    def set_client(self,client):
        self.client = client
        
    def process(self,t):
        if self.start == None:
            self.start = t
            return
        self.client.play(self.audio_buffer[:,self.pos:self.pos+self.client.buffer_size])
        self.pos += self.client.buffer_size
        print self.pos
        if self.pos > len(self.audio_buffer[0]) - self.client.buffer_size:
            self.pos = 0

seaside = Seaside('sounds/seaside')
last = None
with JackClient() as client:
    seaside.set_client(client)
    while True:
        seaside.process(time.time())

