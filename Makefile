###########################
#		DEPEDENCIES
###########################

PYTHON = $(shell which python)
ifeq ($(PYTHON),)
PYTHON = $(shell which python3)
endif


###########################
#		 VARIABLES
###########################

PORT = 5000
ifeq ($(origin IP_ADDRESS), undefined)
IP_ADDRESS != ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1'
else
IP_ADDRESS = IP_ADDRESS
endif


###########################
#	       PATHS
###########################

MODULES := ./modules
SERVER_PROGRAM := $(MODULES)/server.py
CLIENT_PROGRAM := $(MODULES)/client.py

###########################
#	 GAME CONFIGURATIONS
###########################

ifeq ($(origin TIME_LIMIT), undefined)
TIME_LIMIT := 120 # 2 minutes
else
TIME_LIMIT := TIME_LIMIT
endif

###########################
#		 ARGUMENTS
###########################

SERVER_ARG := --ip-address $(IP_ADDRESS) --port $(PORT) --time-limit $(TIME_LIMIT)
CLIENT_ARG := --ip-address $(IP_ADDRESS) --port $(PORT)


###########################
#		  COMMANDS
###########################

clean:
	@rm -rf modules/__pycache__
	@rm -rf modules/__init__.py 

help:
	@echo "Usage:"
	@echo "    header: Output configurations"
	@echo "    start-server: Create a server program on your machine's ip address"
	@echo "    join-server: Join a server program as a client on the server's ip address"

header:
	@echo "IP Address = $(IP_ADDRESS)"
	@echo "Port       = $(PORT)"
	@echo "Time Limit = $(TIME_LIMIT)"

start-server: header
	@echo "Starting Server on $(IP_ADDRESS)"
	@$(PYTHON) $(SERVER_PROGRAM) $(SERVER_ARG)

join-server: header
	@echo "Joining Server on $(IP_ADDRESS)"
	@$(PYTHON) $(CLIENT_PROGRAM) $(CLIENT_ARG)

all: help