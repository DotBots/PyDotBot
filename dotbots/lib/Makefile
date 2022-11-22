.PHONY: all clean test

CC ?= gcc
CFLAGS += -Wall -Werror -Ofast -s

SRC = lh2.c
OBJ = $(SRC:.c=.o)
LIB = $(SRC:.c=.so)

all: $(OBJ) $(LIB)

%.so: %.o
	$(CC) -shared $(LDFLAGS) $< -o $@

%.o: $(SRC)
	$(CC) $(CFLAGS) -o $@ -c $<

clean:
	rm -f lh2.so lh2.o
