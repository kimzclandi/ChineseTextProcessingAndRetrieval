"""Opt-in BM25 query optimization with the historical scoring order retained.

Build once, query many times. As with BM25, rows and scoring parameters must not
be mutated after construction. Extra IDF/normalization tables cost O(V + N)
memory and construction work; this module does not claim faster index building.
"""
from collections import Counter, defaultdict
import heapq
import math
from .retrieval import BM25, tokens


class PreparedBM25(BM25):
    def __init__(self, rows, k1=1.2, b=.75):
        super().__init__(rows, k1=k1, b=b)
        n = len(self.rows)
        self.normalizers = [self.k1*(1-self.b+self.b*length/max(self.avg,1)) for length in self.lengths]
        self.idf = {word:math.log1p((n-len(posting)+.5)/(len(posting)+.5))
                    for word,posting in self.postings.items()}

    def search(self, query, k=3):
        if type(k) is not int or k < 0:
            raise ValueError('k must be a nonnegative integer')
        if k == 0:
            return []
        scores = defaultdict(float)
        for word,qtf in sorted(Counter(tokens(query)).items()):
            posting = self.postings.get(word)
            if not posting:
                continue
            idf = self.idf[word]
            for i,tf in posting:
                # Same floating-point operation order as the frozen reference.
                scores[i] += qtf*idf*tf*(self.k1+1)/(tf+self.normalizers[i])
        ranked = heapq.nsmallest(k, scores, key=lambda i:(-scores[i],self.rows[i]['chunk_id']))
        return [(self.rows[i],scores[i]) for i in ranked]
