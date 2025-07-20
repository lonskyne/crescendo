from collections import deque

class SongQueue:
    def __init__(self):
        self.queue = deque()
        self.current_index = None
        self.max_before = 10

    def add_song(self, song):
        if(self.current_index == None):
            self.current_index = 0

        self.queue.append(song)

    def get_next_song(self):
        if(len(self.queue) > (self.current_index + 1)):
            if(self.current_index > self.max_before):
                self.queue.popleft()
            else:
                self.current_index += 1
        else:
            return None

        return self.queue[self.current_index]

    def get_previous_song(self):
        if(self.current_index > 0):
            self.current_index -= 1

        return self.queue[self.current_index]