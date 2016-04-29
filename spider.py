#-*- coding: UTF-8 -*-
import io
import os
import json
import requests
from time            import sleep
from random          import randint
from pymongo         import MongoClient
from multiprocessing import Process

from qiniu_api import push_file
from diarypage import DiaryPage
from userpage  import UserPage
from page      import get_newest_diary_no
from logger    import dlogger as logger
from constants import DIARY_URL, PEOPLE_URL, ERROR_MAX, \
                      USER_NUM_MIN, USER_NUM_MID, USER_NUM_MID2, \
                      HAVE_NOT_OUTDATE, CURRENT_DIARY_ID

def randomSleep(min, max):
    sleep(randint(min, max))

# Database init
client = MongoClient('localhost', 27017)
db_diarySpider = client.diarySpider
coll_user = db_diarySpider['coll_user']
coll_diary = db_diarySpider['coll_diary']


def userSpider():
    user_error_count = 0
    user_num = USER_NUM_MIN
    while 1:
        if user_num < USER_NUM_MID2 and user_num > USER_NUM_MID:
            user_num = USER_NUM_MID2
            continue

        # If too mang error, sleep 1 hour
        if user_error_count > ERROR_MAX:
            logger.warning("Error count over the max value!!!")
            user_num = user_num - ERROR_MAX
            sleep(3600)
            continue

        if coll_user.find_one({"userid" : str(user_num)}):
            logger.info("This user exist, user number is " + str(user_num))
            user_num = user_num + 1
            continue

        try:
            user_url = PEOPLE_URL + str(user_num)
            user = UserPage(user_url)
            if user.status_code != 200:
                post = {"userid"       : str(user_num), \
                        "status"       : str(1)
                       }
                coll_user.insert(post)
                logger.error("Get url error, url is " + user_url)

                user_num = user_num + 1
                user_error_count = user_error_count + 1
                randomSleep(40, 100)
                continue

            username, userid = user.get_username_and_id()
            joindate = user.get_joindate()
            description = user.get_description()
            icon_img = user.get_icon_img()
            notebooks = user.get_notebooks()

            # Insert into database
            post = {"username"     : username, \
                    "userid"       : userid, \
                    "joindate"     : joindate, \
                    "description"  : description, \
                    "icon_img"     : icon_img, \
                    "notebooks"    : notebooks, \
                    "status"       : str(0)
                   }

            user_file = "user_" + str(user_num)
            with io.open(user_file, 'w', encoding='utf8') as json_file:
                post_string = json.dumps(post, ensure_ascii=False, \
                                         encoding='utf8')
                json_file.write(unicode(post_string))

            push_file(user_file)
            os.remove(user_file)

            coll_user.insert(post)

            logger.info("Get user information successfully, \
                    user number is " + str(user_num))
            user_error_count = 0

        except:
            logger.error("Get user information error, \
                    user number is " + str(user_num))
            user_error_count = user_error_count + 1

        user_num = user_num + 1
        randomSleep(40, 100)

def diary_into_database(diary_no, diary):
    time, content, img_url = diary.get_diary_body()
    if content == HAVE_NOT_OUTDATE:
        post = {"diaryid" : str(diary_no), \
                "status"  : str(1)
               }
        coll_diary.insert(post)
        return True

    img_name = None
    if img_url:
        ret = requests.get(img_url)
        if ret.status_code == 200:
            img_name = 'diary_img_' + str(diary_no) + '_' + \
                       img_url.split('/')[-1]
            with open(img_name, 'wb') as file_object:
                file_object.write(ret.content)

            ret = push_file(img_name)
            os.remove(img_name)

            if ret:
                logger.info("Push dairy image successfully, \
                        image is " + img_name)
        else:
            logger.error("Get image error, url is " + img_url)

    notebook_id, notebook_name = diary.get_notebook_id_name()
    username, userid = diary.get_username_and_id()
    date = diary.get_diary_date()
    comments = diary.get_comments()

    post = {"diaryid"      : str(diary_no), \
            "notebookid"   : notebook_id, \
            "notebookname" : notebook_name, \
            "content"      : content, \
            "img"          : img_name, \
            "userid"       : userid, \
            "username"     : username, \
            "create_date"  : date, \
            "create_time"  : time, \
            "comments"     : comments, \
            "status"       : str(0)
           }

    diary_file = "diary_" + str(diary_no)
    with io.open(diary_file, 'w', encoding='utf8') as json_file:
        post_string = json.dumps(post, ensure_ascii=False, encoding='utf8')
        json_file.write(unicode(post_string))

    push_file(diary_file)
    os.remove(diary_file)
    coll_diary.insert(post)

    return True

def realtimeDiarySpider():
    diary_no = CURRENT_DIARY_ID
    newest_diary_no = get_newest_diary_no()

    while 1:
        if coll_diary.find_one({"diaryid" : str(diary_no)}):
            logger.info("This diary is exist, number is " + str(diary_no))
            diary_no = diary_no + 1
            continue

        diary_url = DIARY_URL + str(diary_no)
        diary = DiaryPage(diary_url)
        if diary.status_code == 200:
            try:
                diary_into_database(diary_no, diary)
                logger.info("Get diary information successfully, \
                        diary number is " + str(diary_no))
                diary_no = diary_no + 1

            except:
                logger.error("Get diary information error, \
                        diary number is " + str(diary_no))
                diary_no = diary_no + 1

        elif diary.status_code == 404:
            post = {"diaryid" : str(diary_no), \
                    "status"  : str(2)
                   }
            coll_diary.insert(post)

            logger.error("Get url error, url is " + diary_url)
            if diary_no <= newest_diary_no:
                diary_no = diary_no + 1
            else:
                newest_diary_no = get_newest_diary_no()

        randomSleep(10, 30)

def start():
    # Create subthread and run
    Process(target=userSpider, args=()).start()
    Process(target=realtimeDiarySpider, args=()).start()

if __name__ == '__main__':
    start()
