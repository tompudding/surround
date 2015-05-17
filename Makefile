CC=gcc

install:
	scp audio.py point.py test.py tom-tv:surround
	#ssh tom-tv 'python audio.py'

#sudo ./ac3jack_cli -S -l
