# CMPT 371 Final Project - Quiz Game

## Project Overview
A multiplayer Quiz Game built with PyGame for graphics and TCP sockets for networking. One player’s machine acts as the server (host), and others connect as clients using direct socket connections. Players compete in a large 2D grid world to collect “microphone” items. Picking up a microphone triggers a quiz question for that player. Correct answers earn points.

## Installation and Setup
Check if you have python installed, then install `pygame`
```
pip install pygame
```
Check if you have `make` installed
```
# linux
sudo-apt update
sudo apt-get install build-essential

# mac
brew install make
```

Install if-config
```
sudo-apt update
sudo apt install net-tools
```

## Usage
```
make help
```
### To Start a Server:
```
make start-server
```
A lobby screen will show up and in the terminal, will output server's ip address and port number for client(s) to connect to.

### To Start a Client and join a Server
```
make join-server IP_ADDRESS=<ip_address> PORT=<port>
```
Input the ip address and port number output from Server.

### Game Configuration
You can customize the game configurations (game configuration is set up by the server):
| Varaibles       | Description                                        | Default Value   |
| --------------- | :------------------------------------------------: | --------------: |
| TIME_LIMIT      | The total time duration of the game before it end. | 120 (2 minutes) |

Example configuration:
```
make start-server TIME_LIMIT=300 # optional input
```

### Debug
If unable to start a server, try setting up your ip address first in the terminal and use it in Makefile:
```
export IP_ADDRESS=$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1')
make start-server IP_ADDRESS=${IP_ADDRESS}
```

## Team Members
- Yuhao Gao 301545007

- JunHang Wu 301435761

- Adam Siergiej 301562042

- Uros Kovacevic 301544276

### References
[Python Socket](https://docs.python.org/3/library/socket.html)
[Receiving Large Amount of Data](https://stackoverflow.com/questions/17667903/python-socket-receive-large-amount-of-data)
[Basic Python TCP Socket Server & Client](https://stackoverflow.com/questions/48406991/basic-python-tcp-socket-server-client)
[PyGame](https://pygame.readthedocs.io/en/latest/1_intro/intro.html)
[Serializing Data](https://docs.python.org/3/library/pickle.html)
