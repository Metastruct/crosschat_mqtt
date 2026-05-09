#!/bin/bash
cd ~/srcds
LD_LIBRARY_PATH=bin:. exec ./srcds_linux -game garrysmod +map gm_construct -nominidumps -heapcheck -nohltv -noaddons -insecure -nogamestats -noshaderapi -noworkshop -disableluarefresh
