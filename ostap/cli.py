
import collections
import os
import chess
from ostap import ostap

def main():
	import argparse

	parser = argparse.ArgumentParser(description='Ostap is a chess game analyzer on top of stockfish')
	parser.add_argument('--engine', dest = 'engine_path', default = 'stockfish',
		help = 'path to stockfish exec')
	parser.add_argument('--engine-threads', type = int, dest = 'engine_threads', default = 2,
		help = 'threads to use')
	parser.add_argument('--engine-hash-tables', type = int, dest = 'engine_hash_tables', default = 256,
		help = 'hash tables size (MB)')
	parser.add_argument('--analysis-multipv', type = int, dest = 'analysis_multipv', default = 3,
		help = 'consider alternative moves')
	parser.add_argument('--analysis-seconds-ply', type = int, dest = 'analysis_seconds_ply', default = 120,
		help = 'time (sec) to analyze each ply')
	parser.add_argument('--analysis-ignore-plies', type = int, dest = 'analysis_ignore_plies', default = 16,
		help = "don't analyze the first plies, usually the opening")
	parser.add_argument('--threshold-error', type = float, dest = 'analysis_threshold_error',
		default = ostap.ANALYSIS_THRESHOLD_ERROR, help = "centipawn score diff for a move to be considered error")
	parser.add_argument('--threshold-first-choice', type = float, dest = 'analysis_threshold_first_choice',
		default = ostap.ANALYSIS_THRESHOLD_FIRST_CHOICE, help = "centipawn score diff between first and last choice")
	parser.add_argument('--output-html', dest = 'output_html', default = None, required = True,
		help = 'directory to output the analysis result in html')
	parser.add_argument('--input-pgn', dest = 'input_pgn', default = None, required = True,
		help = 'PGN file with games to analyze')
	parser.add_argument('--summary-only', dest = 'summary_only', default = False, action = 'store_true',
		help = 'output only the interesting positions')
	args = parser.parse_args()

	engine_options = ostap.ENGINE_OPTIONS
	engine_options.update({
		ostap.ENGINE_OPTION_THREADS: args.engine_threads,
		ostap.ENGINE_OPTION_HASH: args.engine_hash_tables
	})

	analysis_options = ostap.ANALYSIS_OPTIONS
	analysis_options.update({
		ostap.ANALYSIS_OPTION_IGNORE_FIRST_N_PLIES: args.analysis_ignore_plies,
		ostap.ANALYSIS_OPTION_MULTIPV: args.analysis_multipv,
		ostap.ANALYSIS_OPTION_SECONDS_PER_PLY: args.analysis_seconds_ply
	})

	with open(args.input_pgn) as fin:
		game_num = 0
		while pgn := chess.pgn.read_game(fin):
			game_num += 1
			with chess.engine.SimpleEngine.popen_uci(args.engine_path) as engine:
				engine.configure(engine_options)
				game = ostap.analyze(engine, pgn, analysis_options = analysis_options)

				# badges are still WIP, they are arbitrary 1-char but must be sorted
				# in decreasing importance because only the first is currently used.
				# check templates/
				badges = collections.defaultdict(str)
				for pos in ostap.errors(game.positions,
						threshold = args.analysis_threshold_error):
					badges[pos.position.fen] += 'e'
				for pos in ostap.best_first_choice(game.positions,
						threshold = args.analysis_threshold_first_choice):
					badges[pos.position.fen] += 'f'
				for pos in ostap.difficulties(game.positions):
					badges[pos.position.fen] += 'h'

			# TODO relax the 2-digit game limit
			html_out = os.path.join(args.output_html, f"{os.path.basename(args.input_pgn)}.{'%02d' % game_num}.html")
			with open(html_out, 'w') as fout:
				fout.write(ostap.to_html(game, badges, summary_only = args.summary_only))
