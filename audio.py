import jack
import time
import numpy
import wave
import struct
import glob
import os
import random
import sys
import multiprocessing
import threading
import copy
from point import Point

debug_log = open('/tmp/surround_log.txt','wb')

class StdOutWrapper:
    text = []
    def write(self,txt):
        self.text.append(txt)
        if len(self.text) > 500:
            self.text = self.text[:500]
    def get_text(self):
        return ''.join(self.text)

    def flush(self):
        pass

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
        distances = numpy.array([self.falloff((p-point).length()) for point in self.positions],ndmin=2).T
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
        sec = 18.0
        self.pos = 0

        self.input_buffer = numpy.zeros((1,self.buffer_size), 'f')
        self.output_buffer = numpy.ones((6,self.buffer_size), 'f')

    def play(self,output):
        while True:
            try:
                self.client.process(output,self.input_buffer)
            except jack.OutputSyncError:
                continue
            break

    def close(self):
        self.client.deactivate()

def column_stack2(cols):
    """Faster version of numpy.column_stack."""
    rows = len(cols[0])
    assert all(len(col) == rows for col in cols)
    data = numpy.empty((rows, len(cols)))
    for i, d in enumerate(cols):
        data[:,i] = d
    return data

class Sound(object):
    def __init__(self,filename):
        print 'loading',filename
        self.wave = wave.open(filename)
        self.name = os.path.basename(filename)
        if self.wave.getsampwidth() != 2:
            raise TypeError('Expected 2byte wav, got %d byte' % self.wave.getsampwidth())

        self.samples = self.wave.readframes(self.wave.getnframes())
        self.samples = (numpy.fromstring(self.samples,numpy.int16)[::2].astype('f'))/0x8000

        freq = self.wave.getframerate()
        if freq == 44100:
            pass
        elif freq == 22050:
            self.samples = numpy.repeat(self.samples,4)
        else:
            raise ValueError('Unsupported frequency %d' % freq)
        self.path_samples = None
        self.moving = False

    def amplify(self,scale):
        self.samples *= scale

    def set_path(self,path):
        #map samples to path
        if self.path_samples == None:
            self.path_samples = numpy.tile(self.samples, (6,1))

        if path != None:
            self.moving = True
            num_segments = len(path.points)
            samples_per_segment = len(self.samples)/num_segments
            debug_log.write('  generate volumes\n')
            debug_log.flush()
            in_volumes = [speakers.get_volumes(point) for point in path.points]
            volumes = numpy.empty((6,len(self.samples)))
            current_col = 0
            for i,volume in enumerate(in_volumes):
                if i + 1 < len(in_volumes):
                    num = samples_per_segment
                else:
                    #last one
                    num = len(self.samples)-(samples_per_segment*(num_segments-1))
                debug_log.write('    extend volumes %d of %d\n' % (i+1,len(in_volumes)))
                debug_log.flush()
                #volumes.extend([volume]*num)
                volumes[:,current_col:current_col+num] = numpy.repeat(volume,num,axis=1)
                current_col += num
            #debug_log.write('  column stack\n')
            #debug_log.flush()
            #volumes = column_stack2(volumes)
            debug_log.write('  multiply\n')
            debug_log.flush()
            self.path_samples *= volumes


class Environment(object):
    random_sound_period = 3.0
    fade_duration = 2.0
    background = None
    second_background = None
    repeating_sounds = []
    optional_sounds = []
    name = None
    def __init__(self,sounds):
        self.client = None
        self.end_time = None
        self.next_environ = None
        self.fade_in_time = None
        debug_log.write('environ %s\n' % self.name)
        debug_log.flush()
        self.background = copy.deepcopy(sounds[self.background])
        if 'seaside' in self.background.name:
            self.background.amplify(0.7)
        self.background.set_path(None)
        if self.second_background:
            #This is a hack only allowing two backgrounds, but I need this for sunday...
            self.second_background = copy.deepcopy(sounds[self.second_background])
            self.second_background.set_path(None)
            if 'rope' in self.second_background.name:
                self.second_background.amplify(2.5)
        self.repeating_sounds = [copy.deepcopy(sounds[name]) for name in self.repeating_sounds]
        for sound in self.repeating_sounds:
            sound.amplify(6)
            sound.set_path(None)
            #pos = Point(random.random()*2.2,random.random()*2.2)
            #sound.set_path( LinePath(pos,pos,1) )
        self.optional_sounds = [copy.deepcopy(sounds[name]) for name in self.optional_sounds]
        for sound in sounds:
            if sound.startswith('human'):
                self.optional_sounds.append(copy.deepcopy(sounds[sound]))
        for sound in sounds:
            print sound
            if sound.startswith('CAS') and random.random() < 0.3:
                self.optional_sounds.append(copy.deepcopy(sounds[sound]))
            if len(self.optional_sounds) > 10:
                break
        for sound in self.optional_sounds:
            sound.amplify(8)
            pos = Point(random.random()*2.2,random.random()*2.2)
            sound.set_path( LinePath(pos,pos,1) )

        self.timeline = []
        for i in xrange(10):
            self.add_random_sound()

        self.start = None
        self.last_sound = None
        self.reset_audio_buffer()

    def add_random_sound(self):
        if not self.repeating_sounds:
            return
        next_gap = random.expovariate(1/self.random_sound_period)
        if next_gap < 1:
            next_gap = 1.0
        self.timeline.append( (next_gap,random.choice(self.repeating_sounds)) )

    def set_client(self,client):
        self.client = client

    def add_sound_to_buffer(self,sound,random_position = True):
        #Cut the audio_buffer at this point
        self.audio_buffer = self.audio_buffer[:,self.pos:]
        self.pos = 0
        #do we have enough space in the current buffer to fit this sound?
        print 'Adding %d samples' % len(sound.path_samples[0])
        while( len(self.audio_buffer[0]) < len(sound.samples) ):
            self.extend_audio_buffer()
        if sound.moving or not random_position:
            self.audio_buffer[:,:len(sound.samples)] += sound.path_samples
        else:
            #Not moving so choose a random point for it
            self.audio_buffer[:,:len(sound.samples)] += (sound.path_samples*random.choice(points_array))

    def extend_audio_buffer(self):
        extra = numpy.tile(self.background.samples, (6,1)).astype('f')
        self.audio_buffer = numpy.column_stack([self.audio_buffer,extra])

    def reset_audio_buffer(self):
        if self.second_background:
            if len(self.second_background.samples) > len(self.background.samples):
                self.background,self.second_background = self.second_background,self.background
        self.audio_buffer = numpy.tile(self.background.samples, (6,1)).astype('f')
        self.pos = 0
        if self.second_background:
            assert len(self.second_background.samples) <= len(self.background.samples)
            self.audio_buffer[:,:len(self.second_background.samples)] += self.second_background.path_samples
            self.second_background.samples_left = len(self.second_background.samples)

    def process(self,t):
        if self.start == None:
            self.start = t
            self.last_sound = t
            return self
        elapsed = t - self.last_sound
        if self.timeline and elapsed > self.timeline[0][0]:
            x,random_sound = self.timeline.pop(0)
            self.last_sound = t
            self.add_sound_to_buffer(random_sound)
            self.add_random_sound()
        if self.end_time:
            if t > self.end_time:
                self.end_time = None
                out = self.next_environ
                self.next_environ = None
                out.fade_in()
                return out
            partial = float(self.end_time-t)/(self.fade_duration)
            self.client.play(self.audio_buffer[:,self.pos:self.pos+self.client.buffer_size]*partial)
        elif self.fade_in_time:
            if t > self.fade_in_time:
                self.fade_in_time = None
                partial = 1.0
            else:
                partial = 1-(float(self.fade_in_time-t)/self.fade_duration)
            self.client.play(self.audio_buffer[:,self.pos:self.pos+self.client.buffer_size]*partial)
        else:
            self.client.play(self.audio_buffer[:,self.pos:self.pos+self.client.buffer_size])
        if self.second_background:
            self.second_background.samples_left -= self.client.buffer_size
            if self.second_background.samples_left < self.client.buffer_size:
                self.add_sound_to_buffer(self.second_background,random_position = False)
                self.second_background.samples_left = len(self.second_background.samples)
        self.pos += self.client.buffer_size
        if self.pos > len(self.audio_buffer[0]) - self.client.buffer_size:
            self.reset_audio_buffer()
        return self

    def fade_out(self,end_time,next_environ):
        self.end_time = time.time() + self.fade_duration
        self.next_environ = next_environ

    def fade_in(self):
        self.fade_in_time = time.time() + self.fade_duration

class Theme(Environment):
    name = 'Theme'
    background = 'theme.wav'

class Dungeon(Environment):
    name = 'Dungeon'
    background = 'dungeon_background.wav'
    repeating_sounds = ['AMB_E15A.wav',
                        'AMB_E15B.wav',
                        'AMB_E15C.wav',
                        'AMB_E15D.wav',
                        'AMB_E16A.wav',
                        'AMB_E16B.wav',
                        'AMB_E17A.wav',
                        'AMB_E17B.wav',
                        'AMB_E40A.wav',
                        'AMB_E40B.wav',
                        'AMB_E40C.wav']
    optional_sounds = ['lockpick.wav',
                       'horse1.wav',
                       'horse2.wav']

class DungeonPool(Dungeon):
    name = 'Dungeon with Pool'
    second_background = 'pool2.wav'

class DungeonSpooky(Dungeon):
    name = 'Dungeon Spooky'
    second_background = 'dungeon_music.wav'

class DungeonFight(Dungeon):
    name = 'Dungeon Fight'
    background = 'dungeon_fightmusic.wav'
    second_background = Dungeon.background

class DungeonFight1(Dungeon):
    name = 'Dungeon Fight1'
    background = 'dungeon_fightmusic1.wav'
    second_background = Dungeon.background


class DungeonMessage(Dungeon):
    name = 'Dungeon Message'
    second_background = 'foreign.wav'


class DungeonZombies(Dungeon):
    name = 'Dungeon with Zombies'
    repeating_sounds = [('ZOMBI0%d.wav' % i) for i in (1,2,3,4,6)]

class DungeonStream(Dungeon):
    name = 'Dungeon with Stream'
    second_background = 'stream.wav'

class Seaside(Environment):
    name = 'Seaside'
    background = 'seaside_background.wav'
    repeating_sounds = ['AMB_E21.wav',
                        'AMB_E21A.wav',
                        'AMB_E21D.wav',
                        'bird_flapping.wav']
    optional_sounds = ['lockpick.wav',
                       'horse1.wav',
                       'horse2.wav']

class Outside(Enrivonment):
    name = 'outside'
    background = 'ambient.wav'
    repeating_sounds = ['bird_flapping.wav']

class SeasideRopeBridge(Seaside):
    name = 'Seaside with rope bridge'
    second_background = 'wind_rope.wav'

class Tavern(Environment):
    name = 'talking tavern'
    background = 'AMB_M09B.wav'

class WhiteDeer(Tavern):
    name = 'white dear'
    second_background = 'AMB_TAV.wav'

class Town(Environment):
    name = 'town'
    background = 'AMB_M14.wav'


class View(object):
    def __init__(self,h,w,y,x):
        self.width  = w
        self.height = h
        self.startx = x
        self.starty = y
        self.window = curses.newwin(self.height,self.width,self.starty,self.startx)
        self.window.keypad(1)

    def Centre(self,pos):
        pass

    def Select(self,pos):
        pass

    def input(self):
        pass

class Chooser(View):
    label_width = 14
    def __init__(self,parent,h,w,y,x):
        super(Chooser,self).__init__(h,w,y,x)
        self.selected = 0
        self.parent = parent

    def Draw(self,draw_border = False):
        self.window.clear()
        if draw_border:
            self.window.border()

        for i,item in enumerate(self.list):
            if i == self.selected:
                self.selected_pos = i
                self.window.addstr(i+1,1,item.name,curses.A_REVERSE)
            else:
                #print i,line
                self.window.addstr(i+1,1,item.name)
        self.window.refresh()

    def input(self,ch):
        if ch == curses.KEY_UP:
            if self.selected > 0:
                self.selected -= 1
        elif ch == curses.KEY_DOWN:
            if self.selected < len(self.list)-1:
                self.selected += 1
        elif ch == ord(' '):
            self.choose(self.selected)
        elif ch == ord('q'):
            self.parent.quit()
        self.Draw(self is self.parent.current_view)

class EnvironChooser(Chooser):
    def __init__(self,parent,h,w,y,x):
        super(EnvironChooser,self).__init__(parent,h,w,y,x)
        self.list = self.parent.environs

    def choose(self,chosen):
        self.parent.fade_out(self.list[chosen])

class SoundChooser(Chooser):
    def __init__(self,parent,h,w,y,x):
        super(SoundChooser,self).__init__(parent,h,w,y,x)
        self.reset_list()

    def reset_list(self):
        self.list = self.parent.current_environment.optional_sounds
        self.selected = 0

    def choose(self,chosen):
        self.parent.current_environment.add_sound_to_buffer(self.list[chosen])

class SoundControl(object):
    environments = [Theme,
                    DungeonPool,
                    Dungeon,
                    DungeonFight,
                    DungeonFight1,
                    DungeonMessage,
                    DungeonSpooky,
                    DungeonStream,
                    Seaside,
                    SeasideRopeBridge,
                    Tavern,
                    WhiteDeer,
                    Town,
                    ]
    def __init__(self,path,stdscr):
        self.sounds = {}
        for root,dirs,files in os.walk('sounds'):
            for filename in files:
                if filename.endswith('.wav'):
                    self.sounds[filename] = Sound(os.path.join(root,filename))
        self.environs = [environ(self.sounds) for environ in self.environments]
        self.current_environment = self.environs[0]
        self.stdscr = stdscr
        self.thread = None
        self.h,self.w = self.stdscr.getmaxyx()
        self.environ_chooser = EnvironChooser(self,self.h,self.w/2,0,0)
        self.sound_chooser = SoundChooser(self,self.h,self.w/2,0,self.w/2)
        self.views = [self.environ_chooser,self.sound_chooser]
        self.view_index = 0
        self.current_view = self.views[self.view_index]
        self.message_queue = multiprocessing.Queue()
        self.message_queue_back = multiprocessing.Queue()
        self.thread = threading.Thread(target = self.thread_run)
        self.proc = multiprocessing.Process(target = self.process_run, args=(self.message_queue,))
        #self.proc = None
        self.redraw()

    def redraw(self):
        for window in self.sound_chooser,self.environ_chooser:
            window.Draw(window is self.current_view)

    def __enter__(self):
        self.alive = True
        if self.thread:
            self.thread.start()
        if self.proc:
            self.proc.start()
        return self

    def __exit__(self,type, value, traceback):
        self.alive = False
        if self.thread:
            self.thread.join()
        if self.proc:
            self.proc.terminate()
        return False

    def quit(self):
        self.alive = False

    def run(self):
        with JackClient() as client:
            for environment in self.environs:
                environment.set_client(client)
            while self.alive:
                new_environment = self.current_environment.process(time.time())
                if new_environment is not self.current_environment:
                    self.current_environment = new_environment
                    index = self.environs.index(new_environment)
                    self.message_queue_back.put(index)
                    self.sound_chooser.reset_list()
                    self.sound_chooser.Draw()

    def thread_run(self):
        while self.alive:
            ch,view_index,item_index = self.message_queue.get()
            self.view_index = view_index
            self.current_view = self.views[self.view_index]
            self.current_view.selected = item_index
            self.current_view.input(ch)

    # def thread_run(self):
    #     while self.alive:
    #         ch = self.current_view.window.getch()
    #         if ch == ord('\t'):
    #             self.next_view()
    #         else:
    #             self.current_view.input(ch)

    def process_run(self, message_queue):
        self.message_queue = message_queue #Does this do anything?
        self.proc_thread = threading.Thread(target = self.process_thread_run)
        self.proc_thread.start()
        while self.alive:
            ch = self.current_view.window.getch()
            if ch == ord('\t'):
                self.next_view()
            elif ch == ord('q') or ch == ord(' '):
                print 'bam going in the queue'
                self.message_queue.put((ch,self.view_index,self.current_view.selected))
                print self.message_queue
            else:
                self.current_view.input(ch)
        self.proc_thread.join()

    def process_thread_run(self):
        while self.alive:
            environ_index = self.message_queue_back.get()
            self.current_environment = self.environs[environ_index]
            self.sound_chooser.reset_list()
            self.sound_chooser.Draw()

    def next_view(self):
        self.view_index = (self.view_index + 1)%len(self.views)
        self.current_view = self.views[self.view_index]
        self.redraw()

    def fade_out(self,next_environ):
        self.current_environment.fade_out(time.time()+2.0,next_environ)


def main(stdscr):
    curses.curs_set(0)
    with SoundControl('sounds',stdscr) as sounds:
        sounds.run()
        #while True:
        #    time.sleep(1)

def profile_main(stdscr):
    import cProfile
    import re
    cProfile.runctx('old_main(stdscr)',globals(),locals(),'audio_stats')

if __name__ == '__main__':
    #main(None)
    #raise SystemExit
    import curses
    mystdout = StdOutWrapper()
    sys.stdout = mystdout
    sys.stderr = mystdout
    try:
        curses.wrapper(main)
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        sys.stdout.write(mystdout.get_text())
