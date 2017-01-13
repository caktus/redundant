import pickle


def memoize(f):
    memo = {}

    def helper(*args):
        key = pickle.dumps(args)

        if key not in memo:
            memo[key] = f(*args)
        return memo[key]

    return helper
