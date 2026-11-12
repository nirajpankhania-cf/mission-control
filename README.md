# Mission Control

Meridian Launch Services is 90 minutes from a launch. Engineers file anomaly
reports, a pipeline sorts them, plain code sets the go / no_go verdict from
the launch limits, and the Flight Director approves a drafted briefing.

Python 3.9 or later, standard library only. Nothing to install.

## Start the app

```
python3 run.py
```

Then open http://127.0.0.1:8000/ in a browser.

## Run the tests

```
python3 -m unittest
```

The tests never touch the network and need no API key.
