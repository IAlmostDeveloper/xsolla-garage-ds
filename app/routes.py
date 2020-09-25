# -*- coding: utf-8 -*-
import string
import numpy as np
import collections as co

import fasttext

from app import application
from flask import make_response
from flask import jsonify
from flask import request
import json

import re

from nltk.stem.porter import *
import pymorphy2

from nltk import WordPunctTokenizer
from datetime import datetime, timedelta
import time
from dateutil.relativedelta import relativedelta

tokenizer = WordPunctTokenizer()

pymorph = pymorphy2.MorphAnalyzer()


def my_lemming(word):
    return pymorph.parse(word)[0].normal_form


# loading models
model = fasttext.load_model('models/fasttext_fulldata.ftz')


def get_tag(prediction):
    tag = str(prediction[0])
    proba = prediction[1][0]
    tag = tag.replace('__label__', '')
    tag = list(filter(None, re.split('\W|\d', tag)))
    return tag[0] #if (proba > 0.6) else ""


def lemmatize_list_of_words(list_of_words):
    res = []
    for word in list_of_words:
        morph = pymorphy2.MorphAnalyzer()
        p = morph.parse(word)[0]
        new_word = p.normal_form
        res.append(new_word)
    return res


# cleaning text + lemmatization
def get_lemma(text):
    text = re.sub('\[.*\]', '', text)
    text = re.sub("\!", '', text)
    text = re.sub("\'", '', text)
    try:
        words = re.split(' ', text)
        true_words = []
        for word in words:
            m = re.search('(\w+)', word)
            if m is not None:
                good_word = m.group(0)
                true_words.append(good_word)
    except:
        pass

    lemma_list = lemmatize_list_of_words(true_words)
    lemma = ' '.join(lemma_list)
    return lemma


def date_processing(wordString, date_target=datetime.now().strftime("%Y-%m-%d %H:%M:%S")):
    # dicts for days, months and numbers
    numbers = {'тридцать': '30', 'двадцать': '20', 'девятнадцать': '19', 'восемнадцать': '18', 'семнадцать': '17',
               'шесттнадцать': '16', 'пятнадцать': '15',
               'четырнадцать': '14', 'тринадцать': '13', 'двенадцать': '12', 'одиннадцать': '11', 'десять': '10',
               'девять': '09', 'восемь': '08',
               'семь': '07', 'шесть': '06', 'пять': '05', 'четыре': '04', 'третье': '03', 'два': '02', 'первое': '01',
               'первый': '01'}

    days = {'Mon': 1, 'Tue': 2, 'Wed': 3, 'Thu': 4, 'Fri': 5, 'Sat': 6, 'Sun': 7, 'выходной': 6,
            'понедельник': 1, 'вторник': 2, 'среда': 3, 'четверг': 4, 'пятница': 5, 'суббота': 6, 'воскресенье': 7}

    months = {'январт': '01', 'февраль': '02', 'март': '03', 'апрель': '04', 'май': '05', 'июнь': '06', 'июль': '07',
              'август': '08', 'сентябрь': '09', 'октябрь': '10', 'ноябрь': '11', 'декабрь': '12'}

    time_segments = {'вечер': '18:00:00', 'утро': '10:00:00', 'день': '14:00:00', 'обед': '13:00',
                     'вечером': '18:00:00', 'утром': '10:00:00', 'днем': '14:00:00'}

    # deleting text before last token "на"
    if 'на' in wordString:
        wordString = wordString[wordString.rfind('на') + 2:]

    # text clearing from garbage and word lemmatization
    wordString = wordString.lower()
    words = tokenizer.tokenize(re.sub('[-\’,·”–●•№~✅“=#—«"‚»|.?!:;()*^&%+/]', ' ', wordString))
    words = [my_lemming(word) for word in words]

    # case for dates that starts with token 'следующий'
    if 'следующий' in words:
        if 'месяц' in words:
            date_target_dt = datetime(int(date_target[:4]), int(date_target[5:7]),
                                      int(date_target[8:10])) + relativedelta(months=1)
            date_target = date_target_dt.strftime("%Y-%m-%d %H:%M:%S")

        elif 'день' in words or 'вечер' in words or 'утро' in words:
            date_target_dt = datetime(int(date_target[:4]), int(date_target[5:7]), int(date_target[8:10])) + timedelta(
                days=1)
            date_target = date_target_dt.strftime("%Y-%m-%d %H:%M:%S")

        elif 'неделя' in words:
            date_target_dt = datetime(int(date_target[:4]), int(date_target[5:7]),
                                      int(date_target[8:10])) + relativedelta(weeks=1)
            date_target = date_target_dt.strftime("%Y-%m-%d %H:%M:%S")

        # case of day names/weekend after , 'следующие выходные' for example
        else:
            for day in days.keys():
                if day in words:
                    current_date_dt = datetime(int(date_target[:4]), int(date_target[5:7]), int(date_target[8:10]))

                    current_day_name = time.ctime(datetime.timestamp(current_date_dt))[:3]
                    current_day_num = days[current_day_name]
                    target_day_num = days[day]

                    days_delta = target_day_num + (7 - current_day_num)

                    date_target = datetime(int(date_target[:4]), int(date_target[5:7]),
                                           int(date_target[8:10])) + relativedelta(days=days_delta)
                    date_target = date_target.strftime("%Y-%m-%d %H:%M:%S")
                    break

    elif 'завтра' in words:
        date_target = datetime(int(date_target[:4]), int(date_target[5:7]), int(date_target[8:10])) + timedelta(days=1)
        date_target = date_target.strftime("%Y-%m-%d %H:%M:%S")
    elif 'послезавтра' in words:
        date_target = datetime(int(date_target[:4]), int(date_target[5:7]), int(date_target[8:10])) + timedelta(days=2)
        date_target = date_target.strftime("%Y-%m-%d %H:%M:%S")

    # case for days/weekends/defined dates
    else:
        # flag for case definition
        # values: -1 - met day name, 0 - didn't meet any day, 1+ - met particular day number by words or by digits
        day_flag = 0  # -1:

        # checking if there names of days in text
        for day in days.keys():
            if day in words:
                date_dt = datetime(int(date_target[:4]), int(date_target[5:7]), int(date_target[8:10]))

                current_day_name = time.ctime(datetime.timestamp(date_dt))[:3]
                current_day_num = days[current_day_name]
                target_day_num = days[day]

                days_delta = (target_day_num - current_day_num) % 7

                date_target = datetime(int(date_target[:4]), int(date_target[5:7]),
                                       int(date_target[8:10])) + relativedelta(days=days_delta)
                date_target = date_target.strftime("%Y-%m-%d %H:%M:%S")

                day_flag = -1
                break

        # if there are no any days of the week in text
        if day_flag != -1:
            target_day = ''

            for word in words[::-1]:
                if word.isdigit():
                    target_day = word[:2]
                    day_flag = 1
                    break

        if day_flag == 0:
            # checking for any numbers
            for number in numbers.keys():
                if number in words:
                    if day_flag == 0:
                        target_day += numbers[number]
                        day_flag += 1
                    else:
                        target_day = int(target_day) + int(numbers[number])
                        day_flag += 1

        # if programm met particular day by words ow by digits
        if day_flag > 0:
            date_target = date_target[:8] + str(target_day) + date_target[10:]

            # installing the next day to the current date as date_target in case there are no any numbers in text
        if day_flag == 0:
            date_target = date_target[:8] + str(int(date_target[8:10]) + 1) + date_target[10:]

            # cheking for months names
        target_month = date_target[5:7]
        for month in months.keys():
            if month in words:
                target_month = months[month]
                break
        date_target = date_target[:5] + target_month + date_target[7:]

    # 12:00 as default time settings
    date_target = date_target[:-8] + '12:00:00'
    for time_segment in time_segments.keys():
        if time_segment in words:
            date_target = date_target[:-8] + time_segments[time_segment]
            break

    return date_target


#function for title creating
def title_creating(text, n_words=2, part_speech=['NOUN', 'VERB', "INFN"]):
    text = text.lower()
    if text=="":
        return "Твоя пустая заметка"
    words = tokenizer.tokenize(re.sub('[-\’,·”–●•№~✅“=#—«"‚»|.?!:;()*^&%+/]', ' ' , text))
    title_words = []
    curr_n_words = 0

    try:
        for word in words:
            if str(pymorph.parse(word)[0].tag).split(',')[0] in part_speech or word=='не':
                title_words.append(word)
                curr_n_words+=1
                if curr_n_words == n_words:
                    break
        result = " ".join([word for word in title_words])
        result = result[0].upper() + result[1:]
        return result 
    
    except IndexError:
        result = " ".join([word for word in words[:3]])
        result = result[0].upper() + result[1:]
        return result
    


def _build_cors_prelight_response():
    response = make_response()

    response.content_type = "application/json"
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "*")
    response.headers.add("Access-Control-Allow-Methods", "*")

    return response


def _corsify_actual_response(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


@application.route("/", methods=['GET', 'POST'])
def hello():
    resp = {'message': "Hello World!"}
    response = jsonify(resp)

    return response


@application.route("/date_tags", methods=['POST', 'OPTIONS'])
def date_and_tags():
    resp = {'date_target': 'yyyy-mm-dd hh:MM:ss',
            'tag': -1,
            'title':'',
            'message': 'ok'
            }

    if request.method == 'OPTIONS':
        return _build_cors_prelight_response()

    else:
        try:
            getData = request.get_data()
            json_params = json.loads(getData)

            text_content = json_params['text_content']
            text_content = text_content.lower()
            text_content = get_lemma(text_content)

            # predicting category
            prediction = model.predict(text_content, k=1)
            tag = get_tag(prediction)
            resp["tag"] = tag

            # date processing
            current_date = json_params['current_date']
            date_target = date_processing(json_params['text_content'])#, current_date)
            resp['date_target'] = date_target
            
            #title creating
            resp['title'] = title_creating(json_params['text_content'])

        except Exception as e:
            print(e)
            resp['message'] = e

        response = jsonify(resp)

        return _corsify_actual_response(response)
