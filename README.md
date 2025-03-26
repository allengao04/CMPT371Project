# CMPT 371 Final Project - Quiz Game

## Project Overview
A multiplayer Quiz Game built with PyGame for graphics and TCP sockets for networking. One player’s machine acts as the server (host), and others connect as clients using direct socket connections. Players compete in a large 2D grid world to collect “microphone” items. Picking up a microphone triggers a quiz question for that player. Correct answers earn points.

## Installation and Setup
Check if you have python installed, then install `pygame`
```
pip install pygame
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


## Team Members
- Yuhao Gao 301545007

- JunHang Wu 301435761

- Adam Siergiej 301562042

- Uros Kovacevic 301544276
## Technologies Used
## Acknowledgments
