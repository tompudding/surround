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
import pyglet

debug_log = open('/tmp/surround_log.txt','wb')

def temp(dt):
    print 'temp',dt

# music = pyglet.media.load('sounds/theme/theme.wav')
# music.play()
# music1 = pyglet.media.load('sounds/dungeon/dungeon_music.wav')
# music1.play()
# pyglet.clock.schedule_interval(temp, 0.1)
# pyglet.app.run()

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

class Sound(object):
    def __init__(self,filename):
        self.wave = pyglet.media.load(filename, streaming = False)
        self.name = os.path.basename(filename)

    def play(self):
        self.wave.play()

    def amplify(self,scale):
        pass

    def set_path(self,path):
        pass

class RepeatingSound(object):
    def __init__(self,sound):
        self.sound = sound
        self.player = pyglet.media.Player()
        self.sg = pyglet.media.SourceGroup(self.sound.wave.audio_format, '')
        self.sg.queue(self.sound.wave)
        self.sg.loop = True
        self.player.queue(self.sg)

    def play(self):
        self.player.play()

    def stop(self):
        self.player.pause()

    def on_eos(self):
        print 'bloop'

class Environment(object):
    random_sound_period = 3.0
    fade_duration = 2.0
    background_names = []
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
        self.backgrounds = [RepeatingSound(sounds[bg]) for bg in self.background_names]

        self.repeating_sounds = [sounds[name] for name in self.repeating_sounds]
        self.optional_sounds = [sounds[name] for name in self.optional_sounds]
        for sound in sounds:
            if sound.startswith('human'):
                self.optional_sounds.append(sounds[sound])
        for sound in sounds:
            if sound.startswith('CAS') and random.random() < 0.3:
                self.optional_sounds.append(sounds[sound])
            if len(self.optional_sounds) > 10:
                break

        self.timeline = []
        for i in xrange(10):
            self.add_random_sound()

        self.start = None
        self.last_sound = None

    def add_random_sound(self):
        if not self.repeating_sounds:
            return
        next_gap = random.expovariate(1/self.random_sound_period)
        if next_gap < 1:
            next_gap = 1.0
        self.timeline.append( (next_gap,random.choice(self.repeating_sounds)) )

    def add_sound_to_buffer(self,sound,random_position = True):
        #Cut the audio_buffer at this point
        sound.play()
        pass

    def set_volume(self,volume):
        return
        for bg in self.backgrounds:
           bg.player.volume = volume

    def play(self):
        for bg in self.backgrounds:
            bg.play()

    def stop(self):
        for bg in self.backgrounds:
            bg.stop()

    def process(self,t):
        if self.start == None:
            self.start = t
            self.last_sound = t
            self.play()
            return self
        elapsed = t - self.last_sound
        if self.timeline and elapsed > self.timeline[0][0]:
            x,random_sound = self.timeline.pop(0)
            self.last_sound = t
            self.add_sound_to_buffer(random_sound)
            self.add_random_sound()
        if self.next_environ:
            self.stop()
            self.start = None
            out = self.next_environ
            self.next_environ = None
            out.fade_in()
            return out
        elif 0 and self.fade_in_time:
            if t > self.fade_in_time:
                self.fade_in_time = None
                partial = 1.0
            else:
                partial = 1-(float(self.fade_in_time-t)/self.fade_duration)
            self.set_volume(partial)

        return self


    def fade_out(self,end_time,next_environ):
        self.stop()
        #self.end_time = time.time() + self.fade_duration
        self.next_environ = next_environ

    def fade_in(self):
        #self.fade_in_time = time.time() + self.fade_duration
        self.play()

class Theme(Environment):
    name = 'Theme'
    background_names = ['theme.wav']

class Dungeon(Environment):
    name = 'Dungeon'
    background_names = ['dungeon_background.wav']
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
    background_names = Dungeon.background_names + ['pool2.wav']

class DungeonSpooky(Dungeon):
    name = 'Dungeon Spooky'
    background_names = Dungeon.background_names + ['dungeon_music.wav']

class DungeonFight(Dungeon):
    name = 'Dungeon Fight'
    background_names = Dungeon.background_names + ['dungeon_fightmusic.wav']

class DungeonFight1(Dungeon):
    name = 'Dungeon Fight1'
    background_names = Dungeon.background_names + ['dungeon_fightmusic1.wav']


class DungeonMessage(Dungeon):
    name = 'Dungeon Message'
    background_names = Dungeon.background_names + ['foreign.wav']


class DungeonZombies(Dungeon):
    name = 'Dungeon with Zombies'
    repeating_sounds = [('ZOMBI0%d.wav' % i) for i in (1,2,3,4,6)]

class DungeonStream(Dungeon):
    name = 'Dungeon with Stream'
    background_names = Dungeon.background_names + ['stream.wav']

class Seaside(Environment):
    name = 'Seaside'
    background_names = ['seaside_background.wav']
    repeating_sounds = ['AMB_E21.wav',
                        'AMB_E21A.wav',
                        'AMB_E21D.wav',
                        'bird_flapping.wav']
    optional_sounds = ['lockpick.wav',
                       'horse1.wav',
                       'horse2.wav']

class Outside(Environment):
    name = 'outside'
    background_names = ['ambient.wav']
    repeating_sounds = ['bird_flapping.wav']

class SeasideRopeBridge(Seaside):
    name = 'Seaside with rope bridge'
    backgrounds_names = Seaside.backgrounds = ['wind_rope.wav']

class Tavern(Environment):
    name = 'talking tavern'
    background_names = ['AMB_M09B.wav']

class WhiteDeer(Tavern):
    name = 'white dear'
    background_names = Tavern.background_names +  ['AMB_TAV.wav']

class Town(Environment):
    name = 'town'
    background_names = ['AMB_M14.wav']


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
        #self.proc = multiprocessing.Process(target = self.process_run, args=(self.message_queue,))
        #self.proc = None
        self.redraw()

    def redraw(self):
        for window in self.sound_chooser,self.environ_chooser:
            window.Draw(window is self.current_view)

    def __enter__(self):
        pyglet.clock.schedule_interval(self.scheduled, 0.1)
        self.alive = True
        if self.thread:
            self.thread.start()
        return self

    def __exit__(self,type, value, traceback):
        self.alive = False
        pyglet.app.exit()
        if self.thread:
            self.thread.join()
        return False

    def quit(self):
        pyglet.app.exit()
        self.alive = False

    def scheduled(self,dt):
        new_environment = self.current_environment.process(time.time())
        if new_environment is not self.current_environment:
            self.current_environment = new_environment
            index = self.environs.index(new_environment)
            self.message_queue_back.put(index)
            self.sound_chooser.reset_list()
            self.sound_chooser.Draw()

    def thread_run(self):
        while self.alive:
            ch = self.current_view.window.getch()
            if ch == ord('\t'):
                self.next_view()
            self.current_view.input(ch)

    def run(self):
        pyglet.app.run()


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
