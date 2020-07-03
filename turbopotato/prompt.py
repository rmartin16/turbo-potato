import logging
from typing import Union, List

import PyInquirer

from turbopotato.arguments import args
from turbopotato.media_defs import MediaType
from turbopotato.media_defs import MediaName, MediaNameParse, QueryResult
from turbopotato.media import File
from turbopotato.media import Media
from turbopotato.query import TVDBQuery

logger = logging.getLogger('prompt')


class Abort(Exception):
    pass


def print_media_summary(file: File, source: MediaName):
    print('')
    print('Media Information')
    print(f' Title        : {source}')
    print(f' First aired  : {source.first_aired}') if source.first_aired else None
    print(f' Filename     : {file.filepath.name}')
    print(f' Directory    : {file.filepath.parent}')
    print(f'Destination')
    print(f' {file.destination_directory}')
    print(f' {file.destination_filename}')
    print('')


def prompt(media: Media):
    if not args.interactive:
        return

    preempt_series_for_file_groups(media=media)

    try:
        for file in media:
            while choose_match(file=file):
                file.identify_media()
    except Abort:
        for file in media:
            file.skip = True
            file.failure_reason = 'Processing was aborted by user.'


def preempt_series_for_file_groups(media: Media):
    for fg in media.get_file_groups():
        files_w_series_matches: List[File] = [
            file for file in fg.files
            if file.parts.media_type == MediaType.SERIES
               or any(match.media_type == MediaType.SERIES for match in file.query.exact_matches)
               or any(match.media_type == MediaType.SERIES for match in file.query.fuzzy_matches)
        ]
        # files_wo_chosen_one: List[File] = [file for file in files_w_series_matches if not file.chosen_one]
        files_wo_chosen_one: List[File] = list(filter(lambda f: not f.chosen_one, files_w_series_matches))

        if not files_wo_chosen_one:
            continue

        series_id = None
        print('')
        print(f'{fg.name}')
        for file in files_wo_chosen_one:
            print(f' {file.parts}')

            series = dict()
            if file.parts.series_id and file.parts.title:
                series.update({file.parts.series_id: f'{file.parts.title} ({file.parts.network})'})
            series.update({r.series_id: f'{r.title} ({r.network})' for r in file.query.exact_matches})
            series.update({r.series_id: f'{r.title} ({r.network})' for r in file.query.fuzzy_matches})

            print(series)
            choices = [dict(name=v, value=k) for k, v in series.items()]
            choices.insert(0, dict(name='<NONE>', value=None))
            series_id = PyInquirer.prompt(questions={'type': 'list',
                                                     'name': 'series',
                                                     'message': 'Choose a series',
                                                     'choices': choices}
                                          ).get('series')
        if not series_id:
            print('')
            print(f'{fg.name}')
            for file in files_wo_chosen_one:
                print(f' {file.parts}')
            title = PyInquirer.prompt(questions={'type': 'input',
                                                 'name': 'title',
                                                 'message': 'Enter a series title for the group'}
                                      ).get('title')
            if title:
                series_id = None
                series_list = TVDBQuery().query_for_series(title=title)
                if len(series_list) > 1:
                    choices = [
                        dict(name=f'{s["seriesName"]} ({s["network"]})',
                             value=s['id'])
                        for s in series_list
                    ]
                    series_id = PyInquirer.prompt(questions={'type': 'list',
                                                             'name': 'series',
                                                             'message': 'Choose a series',
                                                             'choices': choices}
                                                  ).get('series')
                elif len(series_list) == 1:
                    series_id = series_list[0]['id']

        for file in files_wo_chosen_one:
            if series_id:
                file.parts.series_id = series_id
            else:
                file.parts.title = title
            file.identify_media()


def choose_match(file: File) -> bool:
    """
    Resolve file to media match or just skip the file.
    Return True to re-attempt media identification.
      - set file.parts to new MediaNameParse
    Return False when done with file.
     if skipping file:
      - set file.skip to True
      - set file.failure_reason to rationale
    """

    while True:
        # if a choice was made (either automatically or by the user), let's evaluate it
        if file.chosen_one:
            ans = prompt_send_revise_skip(file, file.chosen_one)

            if ans == 'Send to Media Library':
                return False  # quit out and move on to the next file
            elif ans == 'Manually Enter Information':
                is_new_query, new_media = prompt_new_media_information(file, file.chosen_one)
                if is_new_query:  # query with user-entered information
                    file.parts = new_media
                    return True
                else:  # user didn't want to do another query so try transit with user-entered information
                    file.chosen_one = new_media
                    continue
            elif ans == 'Quit':
                raise Abort
            else:  # default to skipping the file
                file.skip = True
                file.failure_reason = 'File was skipped by user.'
                if ans != 'Skip File':
                    logger.error(f'Unhandled prompt response: {ans}')
                return False

        # present the user with matches; if user chooses a match, set it as chosen and loop back up
        if file.query.exact_matches:
            choices = [
                dict(name=str(match), value=match) for match in file.query.exact_matches
            ]
            media_choice = prompt_list_of_matches(file, 'exact', choices)
            if media_choice:
                file.chosen_one = media_choice
                continue
        if file.query.fuzzy_matches:
            choices = [
                dict(name=f'{str(match)} ({match.fuzzy_match_score})', value=match)
                for match in file.query.fuzzy_matches_sorted
            ]
            media_choice = prompt_list_of_matches(file, 'fuzzy', choices)
            if media_choice:
                file.chosen_one = media_choice
                continue

        # fallback to presenting the user with the parsed filename information
        file.chosen_one = file.parts


def prompt_send_revise_skip(file: File, source: Union[MediaName, MediaNameParse, QueryResult]) -> bool:
    print_media_summary(file=file, source=source)
    choices = ['Manually Enter Information', 'Skip File', PyInquirer.Separator(), 'Quit']
    if file.destination_directory and file.destination_filename:
        choices.insert(0, 'Send to Media Library')
    question = dict(
        type='list',
        name='send',
        message='Choose to send, revise, or skip',
        choices=choices,
    )
    answer = PyInquirer.prompt(question)
    return answer.get('send')


def prompt_new_media_information(file: File,
                                 source: Union[MediaName, MediaNameParse, QueryResult]
                                 ) -> (bool, Union[MediaNameParse, QueryResult]):
    questions = [
        dict(
            type='confirm',
            name='type',
            message='Is this a Series?',
            default=False if source.media_type is MediaType.MOVIE else True
        ),
        dict(
            type='input',
            name='title',
            message='Enter the title of the movie or name of the series',
            default=source.title
        ),
        dict(
            type='input',
            name='year',
            message='Enter a four digit year',
            default=str(source.year or '')
        ),
        dict(
            type='input',
            name='season',
            message='Enter a season number',
            default=str(source.season or '')
        ),
        dict(
            type='input',
            name='episode',
            message='Enter a episode number',
            default=str(source.episode or '')
        ),
        dict(
            type='input',
            name='episodeName',
            message='Enter a episode name',
            default=source.episode_name
        ),
        dict(
            type='confirm',
            name='is_documentary',
            message='Is this a documentary?',
            default=source.is_documentary()
        ),
        dict(
            type='confirm',
            name='is_comedy',
            message='Is this stand-up comedy?',
            default=source.is_comedy()
        ),
        dict(
            type='confirm',
            name='is_query_again',
            message='Query TVDB and TMDB using this information?',
            default=True
        )
    ]
    answers = PyInquirer.prompt(questions)
    media_type = MediaType.SERIES if answers.pop('type') else MediaType.MOVIE
    is_query_again = bool(answers.pop('is_query_again'))
    is_documentary = answers.pop('is_documentary')
    is_comedy = answers.pop('is_comedy')

    if is_query_again:
        return is_query_again, MediaNameParse(media_type=media_type, **answers)
    else:
        genre_ids = set()
        if is_documentary:
            genre_ids.add(99)
        if is_comedy:
            genre_ids.add(35)
        return is_query_again, QueryResult(media_type=media_type,
                                           data=dict(title=answers.get('title'),
                                                     genre_ids=genre_ids,
                                                     release_date=answers.get('year'),
                                                     _series=dict(seriesName=answers.get('title')),
                                                     airedEpisodeNumber=answers.get('episode'),
                                                     airedSeason=answers.get('season'),
                                                     episodeName=answers.get('episodeName')))


def prompt_list_of_matches(file: File, match_type: str, choices: list):
    print_media_summary(file=file, source=file.parts)
    choices.insert(0, dict(name='<NONE>', value=None))
    questions = [
        dict(
            type='list',
            name='match',
            message=f'Choose a {match_type} match',
            choices=choices
        )
    ]
    answers = PyInquirer.prompt(questions)
    return answers.get('match', None)
