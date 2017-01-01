# -*- coding: utf-8 -*-

# Copyright (C) 2016, 2017 - BenBaptist and minecraft-wrapper (AKA 'Wrapper.py')
#  developer(s).
# https://github.com/benbaptist/minecraft-wrapper
# This program is distributed under the terms of the GNU General Public License,
#  version 3 or later.

from __future__ import division

import os
import errno
import sys
import json
import time
import datetime
import socket
import urllib

COLORCODES = {
    "0": "black",
    "1": "dark_blue",
    "2": "dark_green",
    "3": "dark_aqua",
    "4": "dark_red",
    "5": "dark_purple",
    "6": "gold",
    "7": "gray",
    "8": "dark_gray",
    "9": "blue",
    "a": "green",
    "b": "aqua",
    "c": "red",
    "d": "light_purple",
    "e": "yellow",
    "f": "white",
    "r": "\xc2\xa7r",
    "k": "\xc2\xa7k",  # obfuscated
    "l": "\xc2\xa7l",  # bold
    "m": "\xc2\xa7m",  # strikethrough
    "n": "\xc2\xa7n",  # underline
    "o": "\xc2\xa7o",  # italic,
}


def _addgraphics(text='', foreground='white', background='black', options=()):
    """
    encodes text with ANSI graphics codes.
    https://en.wikipedia.org/wiki/ANSI_escape_code#Non-CSI_codes
    options - a tuple of options.
        valid options:
            'bold'
            'italic'
            'underscore'
            'blink'
            'reverse'
            'conceal'
            'reset' - return reset code only
            'no-reset' - don't terminate string with a RESET code

    """
    resetcode = '0'
    fore = {'blue': '34', 'yellow': '33', 'green': '32', 'cyan': '36', 'black': '30',
            'magenta': '35', 'white': '37', 'red': '31'}
    back = {'blue': '44', 'yellow': '43', 'green': '42', 'cyan': '46', 'black': '40',
            'magenta': '45', 'white': '47', 'red': '41'}
    optioncodes = {'bold': '1', 'italic': '3', 'underscore': '4', 'blink': '5', 'reverse': '7', 'conceal': '8'}

    codes = []
    if text == '' and len(options) == 1 and options[0] == 'reset':
        return '\x1b[%sm' % resetcode

    if foreground:
        codes.append(fore[foreground])
    if background:
        codes.append(back[background])

    for option in options:
        if option in optioncodes:
            codes.append(optioncodes[option])
    if 'no-reset' not in options:
        text = '%s\x1b[%sm' % (text, resetcode)
    return '%s%s' % (('\x1b[%sm' % ';'.join(codes)), text)


def config_to_dict_read(filename, filepath):
    """
    reads a disk file with '=' lines (like server.properties) and returns a keyed dictionary.
    """
    config_dict = {}
    if os.path.exists("%s/%s" % (filepath, filename)):
        config_lines = getfileaslines(filename, filepath)
        if not config_lines:
            return {}
        for line_items in config_lines:
            line_args = line_items.split("=", 1)
            if len(line_args) < 2:
                continue
            item_key = getargs(line_args, 0)
            scrubbed_value = scrub_item_value(getargs(line_args, 1))
            config_dict[item_key] = scrubbed_value
    return config_dict


def scrub_item_value(item):
    """
    Takes a text item value and determines if it should be a boolean, integer, or text.. and returns it as the type.
    """
    if not item or len(item) < 1:
        return ""
    if item.lower() == "true":
        return True
    if item.lower() == "false":
        return False
    if str(get_int(item)) == item:  # it is an integer if int(a) = str(a)
        return get_int(item)
    return item


# private static int DataSlotToNetworkSlot(int index)
def _dataslottonetworkslot(index):
    """

    Args:
        index: window slot number?

    Returns: "network slot" - not sure what that is.. player.dat file ?

    """

    # // / < summary >
    # https://gist.github.com/SirCmpwn/459a1691c3dd751db160
    # // / Thanks to some idiot at Mojang
    # // / < / summary >

    if index <= 8:
        index += 36
    elif index == 100:
        index = 8
    elif index == 101:
        index = 7
    elif index == 102:
        index = 6
    elif index == 103:
        index = 5
    elif 83 >= index >= 80:
        index -= 79
    return index


def epoch_to_timestr(epoch_time):
    """
    takes a time represented as integer/string which you supply and converts it to a formatted string.

    :epoch_time: string or integer (in seconds) of epoch time

    :returns: the string version like "2016-04-14 22:05:13 -0400", suitable in ban files.

    """
    tm = int(float(epoch_time))  # allow argument to be passed as a string or integer
    t = datetime.datetime.fromtimestamp(tm)
    pattern = "%Y-%m-%d %H:%M:%S %z"
    return "%s-0100" % t.strftime(pattern)  # the %z does not work below py3.2 - we just create a fake offset.


def find_in_json(jsonlist, keyname, searchvalue):
    # used only by proxy base... TODO probably broken.
    for items in jsonlist:
        if items[keyname] == searchvalue:
            return items
    return None


def _format_bytes(number_raw_bytes):
    """
    takes number of bytes and converts to Kbtye, MiB, GiB, etc... using 4 most significant digits.
    """
    large_bytes = number_raw_bytes / 1073741824
    units = "GiB"
    if large_bytes < 1.0:
        large_bytes *= 1024
        units = "MiB"
    if large_bytes < 1.0:
        large_bytes *= 1024
        units = "KiB"
    # return string tuple (number, units)
    return ("%.4g" % large_bytes), ("%s" % units)


def getargs(arginput, i):
    """
    returns a certain index of argument (without producting an error if our of range, etc).

    :arginput: A list of arguments.

    :i:  index of a desired argument

    :return:  return the 'i'th argument.  if item does not exist, returns ""

    """
    if not i >= len(arginput):
        return arginput[i]
    else:
        return ""


def getargsafter(arginput, i):
    """
    returns all arguments starting at position. (positions start at '0', of course.)

    :arginput: A list of arguments.

    :i: Starting index of argument list

    :return: sub list of arguments

    """
    return " ".join(arginput[i:])


def getjsonfile(filename, directory=".", encodedas="UTF-8"):
    """
    Read a json file and return its contents as a dictionary.

    :filename: filename without extension

    :directory: by default, wrapper script directory.

    :encodedas: the encoding

    Returns: a dictionary if successful. If unsuccessful; None/no data or False (if file/directory not found)

    """
    if not os.path.exists(directory):
        mkdir_p(directory)
    if os.path.exists("%s/%s.json" % (directory, filename)):
        with open("%s/%s.json" % (directory, filename), "r") as f:
            try:
                return json.loads(f.read(), encoding=encodedas)
            except ValueError:
                return None
            #  Exit yielding None (no data)
    else:
        return False  # bad directory or filename


def getfileaslines(filename, directory="."):
    """
    Reads a file with lines and turns it into a list containing those lines.

    :filename: Complete filename

    :directory: by default, wrapper script directory.

    :rtype: list

    returns a list of lines in the file if successful.

        If unsuccessful; None/no data or False (if file/directory not found)

    """
    if not os.path.exists(directory):
        mkdir_p(directory)
    if os.path.exists("%s/%s" % (directory, filename)):
        with open("%s/%s" % (directory, filename), "r") as f:
            try:
                return f.read().splitlines()
            except Exception as e:
                print(_addgraphics("Exception occured while running 'getfileaslines': \n", foreground="red"), e)
                return None
    else:
        return False


def mkdir_p(path):
    """
    A simple way to recursively make a directory under any Python.

    :path: The desired path to create.

    :returns: Nothing - Raises exception if it fails

    """
    try:
        os.makedirs(path, exist_ok=True)  # Python > 3.2
    except TypeError:
        try:
            os.makedirs(path)  # Python > 2.5
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise


def get_int(s):
    """
    returns an integer representations of a string, no matter what the input value.
    returns 0 for values it can't convert

    :s: Any string value.

    """
    try:
        val = int(s)
    except ValueError:
        val = 0
    return val


def isipv4address(addr):
    """
    Returns a Boolean indicating if the address is a valid IPv4 address.

    :addr: Address to validate.

    :return: True or False

    """
    try:
        socket.inet_aton(addr)  # Attempts to convert to an IPv4 address
    except socket.error:  # If it fails, the ip is not in a valid format
        return False
    return True


def processcolorcodes(messagestring):
    """
    Mostly used internally to process old-style color-codes with the & symbol, and returns a JSON chat object.
    message received should be string
    """
    py3 = sys.version_info > (3,)
    if not py3:
        message = messagestring.encode('ascii', 'ignore')
    else:
        message = messagestring  # .encode('ascii', 'ignore')  # encode to bytes

    extras = []
    bold = False
    italic = False
    underline = False
    obfuscated = False
    strikethrough = False
    url = False
    color = "white"
    current = ""

    it = iter(range(len(message)))
    for i in it:
        char = message[i]

        if char not in ("&", u'&'):
            if char == " ":
                url = False
            current += char
        else:
            if url:
                clickevent = {"action": "open_url", "value": current}
            else:
                clickevent = {}

            extras.append({
                "text": current,
                "color": color,
                "obfuscated": obfuscated,
                "underlined": underline,
                "bold": bold,
                "italic": italic,
                "strikethrough": strikethrough,
                "clickEvent": clickevent
            })

            current = ""

            # noinspection PyBroadException
            try:
                code = message[i + 1]
            except:
                break

            if code in "abcdef0123456789":
                try:
                    color = COLORCODES[code]
                except KeyError:
                    color = "white"

            obfuscated = (code == "k")
            bold = (code == "l")
            strikethrough = (code == "m")
            underline = (code == "n")
            italic = (code == "o")

            if code == "&":
                current += "&"
            elif code == "@":
                url = not url
            elif code == "r":
                bold = False
                italic = False
                underline = False
                obfuscated = False
                strikethrough = False
                url = False
                color = "white"

            if sys.version_info > (3,):
                next(it)
            else:
                it.next()

    extras.append({
        "text": current,
        "color": color,
        "obfuscated": obfuscated,
        "underlined": underline,
        "bold": bold,
        "italic": italic,
        "strikethrough": strikethrough
    })
    return json.dumps({"text": "", "extra": extras})


def processoldcolorcodes(message):
    """
    Just replaces text containing the (&) ampersand with section signs instead (§).
    """
    for i in COLORCODES:
        message = message.replace("&" + i, "\xc2\xa7" + i)
    return message


def putjsonfile(data, filename, directory=".", indent_spaces=2, sort=False):
    """
    writes entire data to a json file.
    This is not for appending items to an existing file!

    :data: json dictionary to write

    :filename: filename without extension.

    :directory: by default, wrapper script directory.

    :indent_spaces: indentation level. Pass None for no indents. 2 is the default.

    :sort: whether or not to sort the records for readability.

    :encodedas: This was removed for Python3 compatibility.  Python 3 has no encoding argument for json.dumps.

    :returns: True if successful.

        If unsuccessful;
         None = TypeError,

         False = file/directory not found/accessible

    """
    if not os.path.exists(directory):
        mkdir_p(directory)
    if os.path.exists(directory):
        with open("%s/%s.json" % (directory, filename), "w") as f:
            try:
                f.write(json.dumps(data, ensure_ascii=False, indent=indent_spaces, sort_keys=sort))
            except TypeError:
                return None
            return True
    return False


def read_timestr(mc_time_string):
    """
    The Minecraft server (or wrapper, using epoch_to_timestr) creates a string like this:

         "2016-04-15 16:52:15 -0400"

         This method reads out the date and returns the epoch time (well, really the server local time, I suppose)

    :mc_time_string: minecraft time string.

    :returns: regular seconds from epoch (integer).
            Invalid data (like "forever"), returns 9999999999 (what forever is).

    """

    # create the time for file:
    # time.strftime("%Y-%m-%d %H:%M:%S %z")

    pattern = "%Y-%m-%d %H:%M:%S"  # ' %z' - strptime() function does not the support %z for READING timezones D:
    try:
        epoch = int(time.mktime(time.strptime(mc_time_string[:19], pattern)))
    except ValueError:
        epoch = 9999999999
    return epoch


def _readout(commandtext, description, separator=" - ", pad=15,
             command_text_fg="magenta", command_text_opts=("bold",),
             description_text_fg="yellow", usereadline=True):
    """
    display console text only with no logging - useful for displaying pretty console-only messages.
    Args:
        commandtext: The first text field (magenta)
        description: third text field (green)
        separator: second (middle) field (white text)
        pad: minimum number of characters the command text is padded to
        command_text_fg: Foreground color, magenta by default
        command_text_opts: Tuple of ptions, '(bold,)' by default)
        description_text_fg: description area foreground color
        usereadline: Use default readline  (or 'False', use readchar/readkey (with anti- scroll off capabilities))

    Returns: Just prints to stdout/console for console operator _readout:
      DISPLAYS:
      '[commandtext](padding->)[separator][description]'
    """
    commstyle = _use_style(foreground=command_text_fg, options=command_text_opts)
    descstyle = _use_style(foreground=description_text_fg)
    x = '{0: <%d}' % pad
    commandtextpadded = x.format(commandtext)
    if usereadline:
        print("%s%s%s" % (commstyle(commandtextpadded), separator, descstyle(description)))
    else:
        print("\033[1A%s%s%s\n" % (commstyle(commandtextpadded), separator, descstyle(description)))


def _secondstohuman(seconds):
    results = "None at all!"
    plural = "s"
    if seconds > 0:
        results = "%d seconds" % seconds
    if seconds > 59:
        if (seconds / 60) == 1:
            plural = ""
        results = "%d minute%s" % (seconds / 60, plural)
    if seconds > 3599:
        if (seconds / 3600) == 1:
            plural = ""
        results = "%d hour%s" % (seconds / 3600, plural)
    if seconds > 86400:
        if (seconds / 86400) == 1:
            plural = ""
        results = "%s day%s" % (str(seconds / 86400.0), plural)
    return results


def set_item(item, string_val, filename, path='.'):
    """
    Reads a file with "item=" lines and looks for 'item'.

    If found, it replaces the existing value
    with 'item=string_val'.

    :item: the config item in the file.  Will search the file for occurences of 'item='.

    :string_val: must have a valid __str__ representation (if not an actual string).

    :filename: full filename, including extension.

    :path: defaults to wrappers path.

    :returns:  Boolean indication of success or failure.  None if no item was found.

    """

    if os.path.isfile("%s/%s" % (path, filename)):
        with open("%s/%s" % (path, filename), "r") as f:
            file_contents = f.read()

        searchitem = "%s=" % item
        if searchitem in file_contents:
            current_value = str(file_contents.split(searchitem)[1].split('/n')[0])
            replace_item = "%s%s" % (searchitem, current_value)
            new_item = '%s%s' % (searchitem, string_val)
            new_file = file_contents.replace(replace_item, new_item)
            #with open("%s/%s" % (path, filename), "w") as f:
                #f.write(new_file)
            print("----------\n%s\n----------\n\n" % new_file)
            return True
        return None
    else:
        return False


def _showpage(player, page, items, command, perpage, command_prefix='/'):
    fullcommand = "%s%s" % (command_prefix, command)
    pagecount = len(items) // perpage
    if (int(len(items) // perpage)) != (float(len(items)) / perpage):
        pagecount += 1
    if page >= pagecount or page < 0:
        player.message("&cNo such page '%s'!" % str(page + 1))
        return
    # Padding, for the sake of making it look a bit nicer
    player.message(" ")
    player.message({
        "text": "--- Showing ",
        "color": "dark_green",
        "extra": [{
            "text": "help",
            "clickEvent": {
                "action": "run_command",
                "value": "%shelp" % command_prefix
            }
        }, {
            "text": " page %d of %d ---" % (page + 1, pagecount)
        }]
    })
    for i, v in enumerate(items):
        if not i // perpage == page:
            continue
        player.message(v)
    if pagecount > 1:
        if page > 0:
            prevbutton = {
                "text": "Prev", "underlined": True, "clickEvent":
                    {"action": "run_command", "value": "%s %d" % (fullcommand, page)}
                }
        else:
            prevbutton = {"text": "Prev", "italic": True, "color": "gray"}
        if page <= pagecount:
            nextbutton = {
                "text": "Next", "underlined": True, "clickEvent":
                    {"action": "run_command", "value": "%s %d" % (fullcommand, page + 2)}
                }
        else:
            nextbutton = {"text": "Next", "italic": True, "color": "gray"}
        player.message({
                           "text": "--- ", "color": "dark_green", "extra": [prevbutton, {"text": " | "},
                                                                            nextbutton, {"text": " ---"}]
                           })


def _use_style(foreground='white', background='black', options=()):
    """
    Returns a function with default parameters for addgraphics()
    options - a tuple of options.
        valid options:
            'bold'
            'italic'
            'underscore'
            'blink'
            'reverse'
            'conceal'
            'reset' - return reset code only
            'no-reset' - don't terminate string with a RESET code

    """
    return lambda text: _addgraphics(text, foreground, background, options)


def _chattocolorcodes(jsondata):

    total = _handle_extras(jsondata)
    if "extra" in jsondata:
        for extra in jsondata["extra"]:
            total += _handle_extras(extra)
    return total


def _handle_extras(extra):
    extras = ""
    if "color" in extra:
        extras += _getcolorcode(extra["color"])
    if "text" in extra:
        extras += extra["text"]
    if "string" in extra:
        extras += extra["string"]
    return extras


def _getcolorcode(color):
    for code in COLORCODES:
        if COLORCODES[code] == color:
            return u"\xa7" + code
    return ""


def _create_chat(translateable="death.attack.outOfWorld", insertion="<playername>",
                 click_event_action="suggest_command", click_event_value="/msg <playername> ",
                 hov_event_action="show_entity",
                 hov_event_text_value="{name:\"<playername>\", id:\"3269fd15-5be9-3c2a-af6c-0000000000000\"}",
                 with_text="<playername>", plain_dict_chat=""):
    """
    Creates a json minecraft chat object string (for sending over Protocol).

    :param translateable:
    :param insertion:
    :param click_event_action:
    :param click_event_value:
    :param hov_event_action:
    :param hov_event_text_value:
    :param with_text:
    :param plain_dict_chat:
    :return:

    """
    if not translateable:
        return [json.dumps(plain_dict_chat)]

    chat = {"translate": translateable,
            "with": [
                 {"insertion": insertion,
                  "clickEvent":
                      {"action": click_event_action,
                       "value": click_event_value
                       },
                  "hoverEvent":
                      {
                          "action": hov_event_action,
                          "value":
                              {
                                  "text": hov_event_text_value
                              }
                      },
                  "text": with_text
                  }
             ]
            }
    return [json.dumps(chat)]


def _test_console(message):
    print(message)


def _test_broadcast(message, version_compute=10704, encoding='utf-8'):
    """
    Broadcasts the specified message to all clients connected. message can be a JSON chat object,
    or a string with formatting codes using the § as a prefix
    """

    if isinstance(message, dict):
        if version_compute < 10700:
            _test_console("say %s" % _chattocolorcodes(message))
        else:
            _test_console("tellraw @a %s" % json.dumps(message, encoding=encoding, ensure_ascii=False))
    else:
        if version_compute < 10700:
            temp = processcolorcodes(message)
            _test_console("say %s" % _chattocolorcodes(json.loads(temp)))
        else:
            _test_console("tellraw @a %s" % processcolorcodes(message))


def get_req(something, request):
    # This is a private function used by management.web
    for a in request.split("/")[1:][1].split("?")[1].split("&"):
        if a[0:a.find("=")] == something:
            #PY3 unquote not a urllib (py3) method - impacts: Web mode
            return urllib.unquote(a[a.find("=") + 1:])
    return ""

pathy = "/home/james/Desktop/server"
set_item("eula", "true", "eula.txt", path=pathy)