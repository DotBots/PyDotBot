# BotController-python

This is a bot-controller package to help you choose the type of your controller and easily get started with the DotBot and the Sail Boat.
How to use:<br/>

- Use an nRF52840-DK flashed with the latest firmware from `master` branch here: https://github.com/DotBots/Gateway-firmware-fresh <br/> 
- Connect your nRF52840-DK to your computer via USB and note down its serial port number such as `/dev/tty0`or `COMx` <br/>
- Depending on the use, connect your joystick via USB to your computer <br/>
- Install the latest release of `dotbot-controller` in command line with `pip install dotbot-controller==0.2` <br/> 
- Use the package by entering your controller type, the serial port on which your DK is connected and the baudrate that you work with like this:<br/>
`bot-controller -t joystick -p COM10 -b 115200`
