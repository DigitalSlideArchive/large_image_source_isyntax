Large Image iSyntax Source
==========================

This is a tile source for `large_image <https://github.com/girder/large_image>`_ that reads iSyntax format files using the Philips SDK. 

Requirements
------------

You must obtain the Philips iSyntax SDK.  

Specifically, this use some core libraries and some python modules from the SDK.  The minimum set is the pixelengine, softwarerenderbackend, and softwarerendercontext for each.  You can use the SDK's installation script to add them, but if you use a python virtual environment, you'll need to manually copy or link the python binary files into your virtual environment's site-packages directory.

Python Versions
---------------

At the time of this writing, the Philips SDK only had Python 3.6 and 3.8 support for Ubuntu and 3.7 support for Windows.  In order to allow the core python program to run in your preferred Python version and environment, you can create a secondary Python 3.8 environment and install this module and the ``rpyc`` module in both it and your preferred environment.  In the Python 3.8 environment, run ``rpyc_classic``.  large_image in the main environment will use the 3.8 environment for sources it can't read directly (iSyntax, in this case).
