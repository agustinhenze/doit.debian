export PYTHONPATH=$PWD
touch /tmp/a.py
python3 doit/__main__.py $@ -f /tmp/a.py
