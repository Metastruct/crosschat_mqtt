rsync -rav lua/ srcds@meta3.duckdns.org:srcds/garrysmod/lua/
#rsync -rav cfg/ srcds@meta3.duckdns.org:srcds/garrysmod/cfg/

exec ssh -t srcds@meta3.duckdns.org 'source ~/.bash_profile;~/test_crosschat.sh'
