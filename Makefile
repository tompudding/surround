CC=gcc

install: 
	scp audio.py point.py tom-tv:
	#ssh tom-tv 'python audio.py'

#sudo ./ac3jack_cli -S -l
