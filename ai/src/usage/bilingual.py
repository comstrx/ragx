from core.thread import thread
from .support import main

if __name__ == "__main__":

    thread.run(main("src/usage/candidate.json", "evidence/rag-bilingual.json", bilingual=True))
