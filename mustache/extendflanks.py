import sys
import click
import pygogo as gogo
import pandas as pd
import numpy as np
from snakemake import shell
from random import randint
from mustache import fastatools, embosstools

verbose=True
logger = gogo.Gogo(__name__, verbose=verbose).logger

def get_flank_pairs(flanks, max_direct_repeat_length=20, truncated_flank_length=40, ir_distance_from_end=15):

    column_names = ['contig', 'pos_5p', 'pos_3p', 'seq_count_5p', 'seq_count_3p', 'direct_repeat_length', 'has_IR',
                    'ir_5p', 'ir_3p', 'seq_length_5p', 'seq_length_3p', 'seq_5p', 'seq_3p']
    outpairs = dict()
    flank_count = 0
    for index, row in flanks.iterrows():
        if row.orient != 'R':
            continue
        flank_count += 1

        if flank_count % 250 == 0:
            logger.info("Processed %d 5' flanks and identified %d nearby pairs ..." % (flank_count, len(outpairs)))

        contig, pos = row.contig, row.pos
        right_count, right_seq = row['count'], row.consensus_seq
        trunc_right_seq = truncate_sequence(right_seq, truncated_flank_length)

        min_pos = pos - max_direct_repeat_length
        candidate_pairs = flanks.query('contig == @contig & pos > @min_pos & pos <= @pos & orient == "L"').reset_index(drop=True)

        if candidate_pairs.shape[0] == 0:
            continue

        has_ir_indices = []
        ir_fiveprime = []
        ir_threeprime = []
        for index, candidate_pair in candidate_pairs.iterrows():
            left_seq = candidate_pair.consensus_seq

            trunc_left_seq = truncate_sequence(left_seq, truncated_flank_length, orient='L')

            combined_seq = '-'.join([trunc_right_seq, trunc_left_seq])

            tmp_fasta_path = '/tmp/mustache.flank_pairs.' + str(randint(0, 1e100)) + '.fasta'
            fastatools.write_sequences_to_fasta([combined_seq], tmp_fasta_path)

            tmp_einverted_outfile = '/tmp/mustache.flank_pairs.einverted.' + str(randint(0, 1e100)) + '.out'
            tmp_einverted_outseq = '/tmp/mustache.flank_pairs.einverted.' + str(randint(0, 1e100)) + '.fa'
            embosstools.run_einverted(tmp_fasta_path, outfile=tmp_einverted_outfile, outseq=tmp_einverted_outseq)

            has_ir = False
            ir_length = 0
            keep_ir1 = None
            keep_ir2 = None
            for ir1, ir2 in embosstools.read_emboss_seq_results(tmp_einverted_outseq):
                if pair_has_ir(ir1, ir2, ir_distance_from_end, len(combined_seq)):
                    has_ir = True
                    if len(ir1.seq) > ir_length:
                        keep_ir1 = ir1.seq
                        keep_ir2 = ir2.seq

            candidate_pairs.loc[index, 'has_IR'] = has_ir
            candidate_pairs.loc[index, 'ir_5p'] = keep_ir1
            candidate_pairs.loc[index, 'ir_3p'] = keep_ir2

            shell('rm -f %s' % tmp_fasta_path)
            shell('rm -f %s' % tmp_einverted_outfile)
            shell('rm -f %s' % tmp_einverted_outseq)

        candidate_pairs['diffcount'] = abs(candidate_pairs['count'] - right_count)

        candidate_pairs.sort_values(['has_IR', 'diffcount', 'consensus_seq_length'], ascending=[False, True, False], inplace=True)

        final_pair = candidate_pairs.ix[candidate_pairs.index[0]]
        dr_length = pos-final_pair.pos-1

        outpairs[len(outpairs)] = [contig, pos, final_pair['pos'], right_count, final_pair['count'],
                                   dr_length, final_pair['has_IR'],
                                   final_pair['ir_5p'], final_pair['ir_3p'], len(right_seq),
                                   len(final_pair['consensus_seq']), right_seq, final_pair['consensus_seq']]
    final_pairs = pd.DataFrame.from_dict(outpairs, orient='index', columns=column_names)

    return final_pairs


def pair_has_ir(ir1, ir2, ir_distance_from_end, seqlen):
    if ir_near_5prime_end(ir1, ir_distance_from_end) and ir_near_3prime_end(ir2, ir_distance_from_end, seqlen):
        return True
    return False

def ir_near_5prime_end(ir1, ir_distance_from_end):
    if ir1.fiveprime <= ir_distance_from_end:
        return True
    return False

def ir_near_3prime_end(ir2, ir_distance_from_end, seqlen):
    if ir2.threeprime >= (seqlen - ir_distance_from_end):
        return True
    return False

def truncate_sequence(seq, truncated_seq_length, orient='R'):
    truncated_seq = seq
    if len(truncated_seq) > truncated_seq_length:
        if orient == 'R':
            truncated_seq = truncated_seq[:truncated_seq_length]
        elif orient == 'L':
            truncated_seq = truncated_seq[-truncated_seq_length:]
    return truncated_seq

def _pairflanks(flanksfile, output_file):

    flanks = pd.read_csv(flanksfile, sep='\t')

    flank_pairs = get_flank_pairs(flanks)

    logger.info("Identified %d flank pairs with inverted repeats..." % flank_pairs.shape[0])
    if output_file:
        logger.info("Saving results to file %s" % output_file)
        flank_pairs.to_csv(output_file, sep='\t', index=False)

    return flank_pairs

@click.command()
@click.argument('flanksfile', type=click.Path(exists=True))
@click.option('--output_file', '-o', default='mustache.pairflanks.tsv', help="The output file to save the results.")
def pairflanks(flanksfile, output_file=None):
    _pairflanks(flanksfile, output_file)


if __name__ == '__main__':
    pairflanks()
    #seqs = ['ACGCA', 'ACG', 'ACGC', 'ACGT', 'ACGTC', 'ACGTCA', 'ACGTCAT', 'ACGTCAG', 'ACGTCAT']
    #clusters = get_sequence_clusters(seqs)

    #mytrie = flanktrie.Trie()
    #for s in seqs:
    #    mytrie.add(s)

    #print(mytrie.traverse())
    #print(mytrie.calc_total_shared_words('ACGTCAG', 'ACGTCAT'))
    #print(mytrie.calc_total_unique_shared_words('ACGTCAG', 'ACGTCAT'))
    #print()

    #print(mytrie.traverse())
    #print("DELETING ACGTCAG")
    #mytrie.delete_word('ACG')
    #print(mytrie.traverse())