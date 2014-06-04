import jack
import time
import numpy
import wave
import struct
import glob
import os
import random
from point import Point

class Speakers(object):
    positions = ( Point(0.3,1.1),
                  Point(0.0,1.3),
                  Point(1.9,2.2),
                  Point(0.3,0.0),
                  Point(2.2,0.3),
                  Point(1.3,1.0))
    min_falloff = 0.5
    
    def __init__(self,positions):
        self.positions = positions

    def get_volumes(self,p):
        distances = numpy.array([self.falloff((p-point).length()) for point in self.positions])
        return distances
    
    def falloff(self,distance):
        if distance < self.min_falloff:
            return 1.0
        return 1/((float(distance)/self.min_falloff)**2)

class Path(object):
    def __init__(self,points):
        self.points = points

class LinePath(Path):
    def __init__(self,start,end,num):
        step = (end-start).to_float()/num
        self.points = [start + (step*i) for i in xrange(num+1)]

speakers = Speakers( (Point(0.3,1.1),
                      Point(0.0,1.3),
                      Point(1.9,2.2),
                      Point(0.3,0.0),
                      Point(2.2,0.3),
                      Point(1.3,1.0)))

#Let's make a bunch of random point volumes
points_array = []
for i in xrange(100):
    x = random.random()*2.2
    y = random.random()*2.2
    volume = speakers.get_volumes(Point(x,y))
    points_array.append( numpy.reshape(volume,(6,1)) )

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
        #x = numpy.sin( 2*numpy.pi*4400.0 * (numpy.arange(0,sec*6,1.0/(self.sample_rate),'f')[0:int(self.sample_rate*sec)*6]))
        #print len(x),int(self.sample_rate*sec)
        #self.output = numpy.reshape( x,
        #                             (6, int(self.sample_rate*sec)) ).astype('f')
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
        print 'loading',filename
        self.wave = wave.open(filename)
        if self.wave.getsampwidth() != 2:
            raise TypeError('Expected 2byte wav, got %d byte' % self.wave.getsampwidth())
        #if self.wave.getnchannels() != 1:
        #    raise TypeError('Expected mono sound')
        self.samples = self.wave.readframes(self.wave.getnframes())
        self.samples = (numpy.fromstring(self.samples,numpy.int16)[::2].astype('f'))/0x8000
        #self.samples = numpy.array([(float(struct.unpack('<h',self.wave.readframes(1)[:2])[0])/0x8000) for i in xrange(self.wave.getnframes())]).astype('f')

        freq = self.wave.getframerate()
        if freq == 44100:
            pass
        elif freq == 22050:
            self.samples = numpy.repeat(self.samples,2)
        else:
            raise ValueError('Unsupported frequency %d' % freq)
        self.path_samples = None
        self.moving = False

    def amplify(self,scale):
        self.samples *= scale

    def set_path(self,path):
        #map samples to path
        self.path_samples = numpy.tile(self.samples, (6,1))
        if path != None:
            self.moving = True
            num_segments = len(path.points)
            samples_per_segment = len(self.samples)/num_segments
            in_volumes = [speakers.get_volumes(point) for point in path.points]
            volumes = []
            for i,volume in enumerate(in_volumes):
                if i + 1 < len(in_volumes):
                    num = samples_per_segment
                else:
                    #last one
                    num = len(self.samples)-(samples_per_segment*(num_segments-1))
                volumes.extend([volume]*num)
            volumes = numpy.column_stack(volumes)
            self.path_samples *= volumes
        # for i,volume in enumerate(volumes):
        #     start_sample = i*samples_per_segment
        #     end_sample = start_sample + samples_per_segment
        #     if i+1 == len(volumes):
        #         #last one
        #         end_sample = len(self.samples)-1
            
        #     for j in xrange(start_sample,end_sample):
        #         for k,p_volume in enumerate(volume):
        #             self.path_samples[k][j] *= p_volume
        
        
class Environment(object):
    random_sound_period = 3.0
    def __init__(self,path):
        self.sounds = []
        self.client = None
        for filename in glob.glob(os.path.join(path,'*.wav')):
            sound = Sound(filename)
            if os.path.basename(filename) == 'background.wav':
                self.background = sound
            else:
                sound.amplify(6)
                pos = Point(random.random()*2.2,random.random()*2.2)
                sound.set_path( LinePath(pos,pos,1) )
                self.sounds.append(sound)
        self.timeline = []
        for i in xrange(10):
            self.add_random_sound()
            
        self.start = None
        self.last_sound = None
        self.reset_audio_buffer()

    def add_random_sound(self):
        if not self.sounds:
            return
        next_gap = random.expovariate(1/self.random_sound_period)
        if next_gap < 1:
            next_gap = 1.0
        self.timeline.append( (next_gap,random.choice(self.sounds)) ) 

    def set_client(self,client):
        self.client = client

    def add_sound_to_buffer(self,sound):
        #speaker = random.choice((0,1,2,3,4))
        #Cut the audio_buffer at this point
        self.audio_buffer = self.audio_buffer[:,self.pos:]
        self.pos = 0
        #do we have enough space in the current buffer to fit this sound?
        print 'Adding %d samples' % len(sound.path_samples[0])
        while( len(self.audio_buffer[0]) < len(sound.samples) ):
            self.extend_audio_buffer()
        if sound.moving:
            self.audio_buffer[:,:len(sound.samples)] += sound.path_samples
        else:
            #Not moving so choose a random point for it
            self.audio_buffer[:,:len(sound.samples)] += (sound.path_samples*random.choice(points_array))

    def extend_audio_buffer(self):
        extra = numpy.tile(self.background.samples, (6,1)).astype('f')
        self.audio_buffer = numpy.column_stack([self.audio_buffer,extra])
        
    def reset_audio_buffer(self):
        self.audio_buffer = numpy.tile(self.background.samples, (6,1)).astype('f')
        self.pos = 0
        
    def process(self,t):
        if self.start == None:
            self.start = t
            self.last_sound = t
            return
        elapsed = t - self.last_sound
        if self.timeline and elapsed > self.timeline[0][0]:
            x,random_sound = self.timeline.pop(0)
            self.last_sound = t
            self.add_sound_to_buffer(random_sound)
            self.add_random_sound()
        self.client.play(self.audio_buffer[:,self.pos:self.pos+self.client.buffer_size])
        self.pos += self.client.buffer_size
        if self.pos > len(self.audio_buffer[0]) - self.client.buffer_size:
            self.reset_audio_buffer()

theme = Environment('sounds/theme')
dungeon = Environment('sounds/dungeon')
environs = [theme,dungeon]
current_environment = theme
last = None
with JackClient() as client:
    current_environment.set_client(client)
    while True:
        current_environment.process(time.time())

