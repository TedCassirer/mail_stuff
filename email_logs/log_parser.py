import sys, getopt
import os
from os import path
import re
from collections import defaultdict
import datetime

import smtplib
from os.path import basename
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate

# Will save any exceptions that happened on this date and after in the log files.
DATE_TODAY = datetime.datetime(2016, 04, 19)  # datetime.datetime.today()
# This regex is used to detect stack traces
EXCEPTION_REGEX = re.compile("^\tat")
# Matches a date and time at the begging of the string.
TIME_REGEX = re.compile("(^\d{4}\-\d{2}\-\d{2})\s(\d{2}:\d{2}:\d{2})")
# First element in the list is the trace-count, second are the timestamps, third saves all the first lines of the trace.
# Currently the program only makes use of the first head of each type of stacktrace
exceptions = defaultdict(lambda: [0, [], []])

def registerException(exc, lastSeenTime):
    head, rest = exc.split("\n", 1)
    exceptions[rest][0] += 1
    exceptions[rest][1].append(lastSeenTime[-8:])
    exceptions[rest][2].append(head)


def processFile(filePath):
    with open(filePath, "r") as log_file:
        currentMatch = ""
        previousLine = None
        sameBlock = False
        lastSeenDate = None
        for line in log_file.readlines():
            dateMatch = TIME_REGEX.match(line)
            if dateMatch:
                traceDate = datetime.datetime.strptime(dateMatch.group(0), "%Y-%m-%d %H:%M:%S")
                lastSeenDate = traceDate
                lastSeenTime = dateMatch.group(0)
            if (lastSeenDate and DATE_TODAY > lastSeenDate) or line == "\n":
                continue
            match = EXCEPTION_REGEX.search(line)
            if match and sameBlock:
                currentMatch += line
            elif match:
                sameBlock = True
                currentMatch += previousLine + line
            elif sameBlock:
                sameBlock = False
                if not line.startswith("java"):
                    registerException(currentMatch, lastSeenTime)
                    currentMatch = ""
                else:
                    currentMatch += "\n"
            previousLine = line
        # If last line in file was a stack trace
        if sameBlock:
            registerException(currentMatch)


def send_mail(send_from, send_to, subject, text, files=None):
    assert isinstance(send_to, list)
    msg = MIMEMultipart(
        From=send_from,
        To=', '.join(send_to),
        Date=formatdate(localtime=True),
        Subject=subject
    )
    msg.attach(MIMEText(text))

    for f in files or []:
        with open(f, "rb") as fil:
            msg.attach(MIMEApplication(
                fil.read(),
                Content_Disposition='attachment; filename="%s"' % basename(f),
                Name=basename(f)
            ))

    smtp = smtplib.SMTP('smtp.gmail.com', 587)
    smtp.ehlo()
    smtp.starttls()
    import base64
    # This is very safe and uncrackable. base64 has not been solved yet.
    pw = base64.b64decode(open("pw").read())
    smtp.login(send_from, pw)
    smtp.sendmail(send_from, send_to, msg.as_string())
    smtp.close()



def main(argv):
    output_directory = "exception_logs"
    input_directory = "logs"
    sender = "ted.cassirer@gmail.com"
    try:
        opts, args = getopt.getopt(argv, "i:o:s:r:", ["input_directory=", "output_directory=", "sender=", "receiver="])
    except getopt.GetoptError:
        print 'log_parser.py -i <input directory> -o <output directory> -s <sender> -r <receivers>'
        print "Example: python log_parser -i logs/application -o output_directory/ -s my.mail@gmail.com " \
              "-r person@mail.com,other.guy@mail.com"
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-i", "--input"):
            input_directory = arg
        elif opt in ("-o", "--output"):
            output_directory = arg
        elif opt in ("-s", "--sender"):
            sender = arg
        elif opt in ("-r", "--receivers"):
            receivers = arg.split(',')
        else:
            assert False, "unhandled option"

    logs = [path.join(input_directory, f) for f in os.listdir(input_directory)]
    new_files = []
    for f in logs:
        processFile(f)
        i = f.find(path.sep)
        if not path.exists(output_directory):
            os.makedirs(output_directory)
        new_file = path.join(output_directory, DATE_TODAY.isoformat()[:10] + "_exceptions_" + f[i + 1:])
        new_files.append(new_file)
        with open(new_file, "w") as output:
            for exception in sorted(exceptions.items(), key=lambda e: e[1][0], reverse=True):
                out = DATE_TODAY.isoformat()[:10] + \
                      "\n{count} found:\n{head}\n{trace}\n{time}".format(
                          count=exception[1][0], head=exception[1][2][0], trace=exception[0], time=str(exception[1][1])) + \
                      "\n\n" + 100 * "-" + "\n"
                output.write(out)

    send_mail(sender, receivers, "Exceptions'n stuff", "It worked!", new_files)

if __name__ == "__main__":
    main(sys.argv[1:])