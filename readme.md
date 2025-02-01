# GoPro USB HTTP API Control

Testing out the HTTP API for taking photos and immediately downloading them with a GoPro via the HTTP API using USB-C.

The capture rate is pretty slow, like 1 pic every 4-5 seconds max speed, though I think it can be done much better. The HTTP request system isn't super stable, the GoPro HTTP server can be unresponsive when writing to SD/taking photos. I have managed to freeze the GoPro a couples times by sending too many requests (required power cycle) so be aware of that.

This script was written using a GoPro Hero 10 for testing. It should work on later models too, but there is a far more efficient way to download the latest media using [get last media API call](https://gopro.github.io/OpenGoPro/http#tag/Query/operation/OGP_GET_LAST_MEDIA), rather than polling the camera status. This should be implemented if it is available to you.

Also, on the GoPro Hero 13 there is another improvement which could be made using the [GoPro Labs firmware](https://github.com/gopro/labs), by activating regular HTTP (rather than HTTPS) for faster requests, see [GoPro Labs extension features](https://gopro.github.io/labs/control/extensions/). 

Also, there are USB startup commands and power up with any power source options available with GoPro Labs firmware if the camera is to be used in situation where the touch screen is inaccessible and BLE is not available. 

### Environment Setup
1. OPTIONAL: Create venv and activate it.
2. Install python dependencies:
	```pip install -r requirements.txt```

### Usage
1. Find GoPro serial number (you can find this in settings>about)/
2. Execute period capture
	```python periodic_capture.py --ip 172.2X.1YZ.51 --port 8080```
	Where XYZ is the last 3 digits of the serial number.
3. Script sets up GoPro for external USB control.
4. Periodically captures full resolution photo and downloads it.

### TODO
- Add preview stream while taking a video or timelapse. Unfortunately the HTTP API is not available while recording video or timelapse.
- Test with new GoPro models
- Clean up argparse parameters