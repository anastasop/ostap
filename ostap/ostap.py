
import collections
import itertools
import os.path

import chess
import chess.engine
import chess.pgn
import chess.svg
import jinja2

ENGINE_OPTION_THREADS = 'Threads'
ENGINE_OPTION_HASH = 'Hash'
ENGINE_OPTIONS = {
	ENGINE_OPTION_THREADS: 4,
	ENGINE_OPTION_HASH: 256
}

ANALYSIS_OPTION_IGNORE_FIRST_N_PLIES = 'ignore_first_n_plies'
ANALYSIS_OPTION_MULTIPV = 'multipv'
ANALYSIS_OPTION_SECONDS_PER_PLY = 'seconds_per_ply'
ANALYSIS_OPTIONS = {
	ANALYSIS_OPTION_IGNORE_FIRST_N_PLIES: 16,
	ANALYSIS_OPTION_MULTIPV: 3,
	ANALYSIS_OPTION_SECONDS_PER_PLY: 60
}

ANALYSIS_THRESHOLD_ERROR = 0.75
ANALYSIS_THRESHOLD_FIRST_CHOICE = 1.5

#
# The following types are aligned with the returned tuples of 'evaluation'
#

# Move is a tuple with a move in san and uci, for example ('Nc3', 'b1c3')
Move = collections.namedtuple('Move', 'san uci')

# Evaluation is a move with the engine score in centipawns from the white pov,
# for example (0.38, ('Nb5', 'd4b5'))
Evaluation = collections.namedtuple('Evaluation', 'score move')

# Position contains the fen and the list of engine evaluations,
# for example
# ('r1b1kb1r/ppqppppp/2n2n2/8/3NP3/4B3/PPP2PPP/RN1QKB1R w KQkq - 3 6',
#   (38, 38),
#   [(0.55, ('Nc3', 'b1c3')), (0.38, ('Nb5', 'd4b5'))])
Position = collections.namedtuple('Position', 'fen evaluations')

# PositionWithMove is a Position and the Move played, for example
# (('r1b1kb1r/ppqppppp/2n2n2/8/3NP3/4B3/PPP2PPP/RN1QKB1R w KQkq - 3 6',
#   (38, 38),
#   [(0.55, ('Nc3', 'b1c3')), (0.38, ('Nb5', 'd4b5'))]),
#   ('Nd2', 'b1d2'))
PositionWithMove = collections.namedtuple('PositionWithMove', 'position move_played')

# Game is a dict with the PGN headers and a list of PositionWithMove
Game = collections.namedtuple('Game', 'headers positions')


def analyze(engine, game, analysis_options = ANALYSIS_OPTIONS):
	"""Uses the engine to analyze the game and returns the analysis."""

	moves = list(game.mainline_moves())
	board = game.board()

	ignore = analysis_options[ANALYSIS_OPTION_IGNORE_FIRST_N_PLIES]

	for move in moves[0:ignore]:
		board.push(move)

	positions = []
	for move in moves[ignore:]:
		ev = evaluation(engine, board, analysis_options)
		positions.append(PositionWithMove(ev, Move(move and board.san(move), move and move.uci())))
		board.push(move)
	last_ev = evaluation(engine, board, analysis_options = analysis_options)
	positions.append(PositionWithMove(last_ev, Move(None, None)))
	return Game(dict(game.headers), positions)


def evaluation(engine, board, analysis_options = ANALYSIS_OPTIONS):
	"""Engine analyzes the board position and returns a Position."""

	# passing to the UCI engine the board as the game object
	# ensures same game behavior
	infos = engine.analyse(board, game = board,
		limit = chess.engine.Limit(
			time = analysis_options[ANALYSIS_OPTION_SECONDS_PER_PLY]),
		multipv = analysis_options[ANALYSIS_OPTION_MULTIPV],
		info = chess.engine.INFO_ALL)

	# extract the notation for the move suggested by the engine in this info.
	# final positions like mate, stalemate do not have move suggestions.
	def move_suggested(info, board):
		if 'pv' in info:
			return Move(board.san(info['pv'][0]), info['pv'][0].uci())
		return Move(None, None)

	return Position(fen = board.fen(),
		evaluations = [
			Evaluation(info['score'].white().score(mate_score=1000)/100.0,
			move_suggested(info, board)) for info in infos])


def errors(positions, threshold = ANALYSIS_THRESHOLD_ERROR):
	"""Filters positions for errors, the move played is significantly worse than
	the engine's first choice"""

	# simulate each_cons. [e1, e2, e3] -> [(e1, e2), (e2, e3)]
	cur, ntx = itertools.tee(positions, 2)
	next(ntx, None)

	def score_diff(pos):
		return abs(pos[1].position.evaluations[0].score - pos[0].position.evaluations[0].score)

	return [pos[0] for pos in zip(cur, ntx) if score_diff(pos) >= threshold]


def difficulties(positions):
	"""Filters positions where the evalution fluctuates, the advantages
	alternates between white and black"""

	def sign(x):
		if x > 0.0:
			return 1
		if x < 0.0:
			return -1
		return 0

	def fluctuates(pos):
		return len(set([sign(ev.score) for ev in pos.position.evaluations])) > 1

	return [pos for pos in positions if fluctuates(pos)]


def best_first_choice(positions, threshold = ANALYSIS_THRESHOLD_FIRST_CHOICE):
	"""Filters positions where the first move choice is significantly
	better than the others"""

	def score_diff(pos):
		return abs(pos.position.evaluations[0].score - pos.position.evaluations[-1].score)

	return [pos for pos in positions if score_diff(pos) >= threshold]


def to_html(game, badges, summary_only):
	"""Renders the output of analyze to a nice html file. Check templates/"""

	if summary_only:
		positions = []
		it = iter(game.positions)
		while pos := next(it, None):
			if badge := badges[pos.position.fen]:
				positions.append(pos)
				if badge[0] == 'e':
					# for errors, add also the next position to
					# show the correct move
					positions.append(next(it, None))
	else:
		positions = game.positions

	svgs = []
	for d in positions:
		svg = chess.svg.board(chess.Board(d.position.fen), size = 400, coordinates = False)
		svgs.append(svg)
	diagrams = zip(positions, svgs)

	env = jinja2.Environment(loader = jinja2.PackageLoader('ostap', 'templates'),
		autoescape = True)
	game_tmpl = env.get_template('game.html')
	game_html = game_tmpl.render(headers = game.headers, diagrams = diagrams,
		badges = badges)

	return game_html
