# This creates new tests and stores them in a remote mongdodb.
import time
import click
from pymongo import MongoClient
import datetime
import random
import configparser
import os
from terminaltables import SingleTable
import gspread
from oauth2client.service_account import ServiceAccountCredentials
scope = ['https://spreadsheets.google.com/feeds']

#Notice that you'll need to create the file with credentials for Google Drive API
creds = ServiceAccountCredentials.from_json_keyfile_name('client_secret.json', scope)
client = gspread.authorize(creds)


# First lets create a click command to create one
@click.group()
def create():
    pass


# Don't forget to cover the password, find it in click documentation
@create.command()
@click.option('--host_name', prompt="Host Name")
@click.option('--db_name', prompt="DB Name")
@click.option('--user_name', prompt="User")
@click.option('--password', prompt="Password")
def configdb(host_name, db_name, user_name, password):
    """Sets up the database to use"""
    clear_screen()
    # Check if there is a valid config if not then go ahead, otherwise tell the user
    if check_config():
        print("There is already a configuration")
        ask = input("Do you want to overwrite it? [y/n]")
        if ask.lower() != "y":
            print("No change has been made")
            return

    # Reconfig
    client = MongoClient(host_name, 27017)
    db = client[db_name]
    try:
        connect = db.authenticate(user_name, password)
        print('It works and you\'re in')

    except (Exception):
        print("You can't access that server or database")
        return

    config = configparser.ConfigParser()
    config['SERVER'] = {
        "host_name": host_name,
        "db_name": db_name,
        "user_name": user_name,
        "password": password
    }
    with open('config.ini', 'w') as configfile:
        config.write(configfile)
    print("Configuration saved!")

def check_config():
    config = configparser.ConfigParser()
    if config.read('config.ini') == []:
        return False
    else:
        return True

def connect():
    config = configparser.ConfigParser()
    config.read('config.ini')
    host_name = config['SERVER']['host_name']
    db_name = config['SERVER']['db_name']
    user_name = config['SERVER']['user_name']
    password = config['SERVER']['password']
    client = MongoClient("mongodb://" + user_name + ":" + password + "@" + host_name + ":27017")
    db = client[db_name]
    return db


@create.command()
def edittest():
    """Edits an already existing test or creates a new test"""
    clear_screen()
    if check_config() == False:
        print("No DB configured")
        return
    db = connect()
    selected_skill = skill_selector(db)

    selected_page = page_selector(selected_skill, db)
    cursor = db.pages.find({"skill": selected_skill, "title": selected_page})
    for document in cursor:
        print("Your choice is:\t", document['title'])
    if 'test' in document:
        print("This test already has", len(document['test']), "questions")
    add_questions(selected_page, selected_skill, db)
    cursor = db.pages.find({"skill": selected_skill, "title": selected_page})
    for document in cursor:
        ledocument = document
    print("This page has now:", len(ledocument['test']), "questions")


@create.command()
def createfromdrive():
    """Updates an entire skill test base using data from a spreadsheet in G.Drive"""
    clear_screen()
    if check_config() == False:
        print("No DB configured")
        return
    db = connect()
    selected_skill = skill_selector(db)

    # Select a G.Drive spreadsheet with the same name
    file = client.open(selected_skill)

    # Select each one of the sheets
    for sheet in file.worksheets():
        questions_and_answer = sheet.get_all_records()
        # Get the page name
        selected_page = sheet.title
        # Delete test if existing
        db.pages.update({"skill": selected_skill, "title": selected_page}, {"$unset": {"test": []}})
        for single in questions_and_answer:
            # Reformat to be what the DB needs.
            answers = []
            answers.append(single['Correct'])
            # This gives up to 10 possible fake answers.
            for index in range(1,10):
                field = 'Fake' + str(index)
                #import pdb; pdb.set_trace()
                if single.get(field) and single[field] != "":
                    answers.append(single[field])
            question_and_answers = {
                "question": single['Question'],
                "answers": answers,
            }

            # Update it
            results = db.pages.update(
                {"skill": selected_skill, "title": selected_page},
                {"$push": {"test": question_and_answers}}
            )
        if results['updatedExisting'] == False:
            print("Page doesn't exist")
            page = create_page(selected_page, selected_skill, db)
            print("Page", page, "has been created")
            results = db.pages.update(
                {"skill": selected_skill, "title": selected_page},
                {"$push": {"test": question_and_answers}}
            )

    # Might want to be more informative in the future.
    print("Tests imported successfully")


def skill_selector(db):
    clear_screen()
    print('Select a skill')
    # First show all the skills and select one
    cursor = db.skills.find()
    choice = []
    index = 1
    data = []
    data.append(["#", "Skill", "Last Tested", "Level"])
    for document in cursor:
        choice.append(document['title'])
        if document.get('scores'):
            last_date = document['scores'][-1]['date']
            last_tested = '{:%d-%b-%Y}'.format(last_date)
        else:
            last_tested = "Never"
        data.append([index, document['title'], last_tested, document['mastery']])
        index += 1
    table = SingleTable(data)
    print(table.table)
    user_answer = int(input("Please select a skill: ")) - 1
    selected_skill = choice[user_answer]
    return selected_skill


def page_selector(selected_skill, db):
    # Show the pages of that skill and which one have a test already
    clear_screen()
    cursor = db.pages.find({"skill": selected_skill})
    choice = []
    index = 1
    data = []
    data.append(["#", "Title", "Has Test?", "Questions"])
    for document in cursor:
        choice.append(document['title'])
        if document.get('test'):
            questions = len(document['test'])
        else:
            questions = "None"
        data.append([index,document["title"], "Yes" if 'test' in document else "No", questions])
        index += 1
    table = SingleTable(data)
    print(table.table)
    user_answer = input("Please select a page or 'n' for new page:")
    if user_answer == "n":
        page_name = input("Write the name of the page: ")
        create_page(page_name, selected_skill, db)
    else:
        user_answer = int(user_answer) -1
        selected_page = choice[user_answer]
        return selected_page

def create_page(page_name, selected_skill, db):
    new_page = {
        "title": page_name,
        "content": "Self-generated by Knowledge Tester",
        "skill": selected_skill,
        "editDate": "2017-09-09T00:09:50.357Z",
        "imgURL": "empty"
    }
    results = db.pages.insert_one(new_page)
    print("Page is being generated")
    return page_name


def add_questions(selected_page, selected_skill, db):
    choice = "y"
    while choice == "y":
        clear_screen()
        question = input("The question:")
        print("The question is:", question)
        print("You can introduce as many answers as you want, to stop type one spacebar then intro")
        user_input = ""
        answers = []
        while user_input != " ":
            user_input = input("Answer:")
            if user_input == " ":
                break
            else:
                answers.append(user_input)
        print("These are the answers:")
        index = 0
        for answer in answers:
            print(str(index + 1) + ")", answer)
            index += 1
        question_and_answers = {
            "question": question,
            "answers": answers,
        }

        results = db.pages.update(
            {"skill": selected_skill, "title": selected_page},
            {"$push": {"test": question_and_answers}}
        )
        choice = input("Do you want to add another question [y/n]:").lower()


@create.command()
def testme():
    """Tests your knowledge of a page"""
    clear_screen()
    if check_config() == False:
        print("No DB configured")
        return
    db = connect()
    selected_skill = skill_selector(db)
    selected_page = page_selector(selected_skill, db)
    cursor = db.pages.find({"skill": selected_skill, "title": selected_page})
    for document in cursor:
        if 'test' in document:
            tests = document['test']
        else:
            print("There are no tests for that page")
            return

    # This should be limited to 20 questions, don't forget to change that.
    totals = 0

    if len(tests) < 20:
        print("Can't test you while the tests are less than 20")
        print("Currently the page has only", len(tests), "tests")
        return
    selected = random.sample(tests, 20)
    for test in selected:
        clear_screen()
        data = []
        data.append(["#", test['question']])
        answers = test['answers']

        unsorted = random.sample(answers, len(answers))
        for answer in unsorted:
            data.append([unsorted.index(answer) + 1, answer])
        data.append([totals, "Current Score",])
        table = SingleTable(data)
        table.inner_footing_row_border = True
        print(table.table)
        # The correct one is always the first
        correct = test['answers'][0]
        try:
            user_answer = int(input("Please enter the index of the right answer: ")) - 1
        except (ValueError):
            print("That's not a valid answer")
            time.sleep(2)
            continue

        #Validate input
        if int(user_answer) in range(len(test['answers'])):
            if unsorted[user_answer] == correct:
                totals += 1
                print("Right answer, your points are: " + str(totals) + " points")
            else:
                print("Wrong answer, moving on")
        else:
            print("That's not a valid answer")
            time.sleep(2)
            continue

    # From here is about what to do with the test:
    now = datetime.datetime.now()

    # This uploads the results
    results = db.pages.update(
        {"skill": selected_skill, "title": selected_page},
        {"$push": {"scores": {"score": totals, "date": now}}}
    )
    clear_screen()
    print("You got:", totals, "questions correct out of 20")
    percentage = str(round(totals / 20 * 100)) + "%"
    print("That's a score of", percentage, "right")
    print("Goodbye!")


@create.command()
def testskill():
    """Tests a whole skill by taking a sample from different pages"""
    clear_screen()
    if check_config() == False:
        print("No DB configured")
        return
    db = connect()
    selected_skill = skill_selector(db)
    tests = []
    cursor = db.pages.find({"skill": selected_skill})
    for document in cursor:
        if 'test' in document:
            tests.extend(document['test'])
    if len(tests) < 20:
        print("Can't test you while the tests are less than 20")
        print("Currently the skill has only", len(tests), "tests")
        return
    totals = 0
    selected = random.sample(tests, 20)

    for test in selected:
        clear_screen()
        data = []
        data.append(["#", test['question']])
        answers = test['answers']
        unsorted = random.sample(answers, len(answers))
        for answer in unsorted:
            data.append([unsorted.index(answer) + 1, answer])
        data.append([totals, "Current Score",])
        table = SingleTable(data)
        table.inner_footing_row_border = True
        print(table.table)
        # The correct one is always the first
        correct = test['answers'][0]
        try:
            user_answer = int(input("Please enter the index of the right answer: ")) - 1
        except (ValueError):
            print("That's not a valid answer")
            time.sleep(2)
            continue

        #Validate input
        if int(user_answer) in range(len(test['answers'])):
            if unsorted[user_answer] == correct:
                totals += 1
                print("Right answer, your points are: " + str(totals) + " points")
            else:
                print("Wrong answer, moving on")
        else:
            print("That's not a valid answer")
            time.sleep(2)
            continue

    # From here is about what to do with the test:
    now = datetime.datetime.now()

    # This uploads the results
    results = db.skills.update(
        {"title": selected_skill},
        {"$push": {"scores": {"score": totals, "date": now}}}
    )
    clear_screen()
    print("You got:", totals, "questions correct out of 20")
    percentage = str(round(totals / 20 * 100)) + "%"
    print("That's a score of", percentage, "right")
    if totals <= 15:
        level = "Learning"
    else:
        level = "Familiar"

    mastery = db.skills.update(
        {"title": selected_skill},
        {"$set": {"mastery": level}}
    )
    print("Level updated to:", level)
    print("Goodbye!")

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

if __name__ == '__main__':
    create()
