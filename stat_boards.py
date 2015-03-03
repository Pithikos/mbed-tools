'''
This tool can be run on Linux to find information about mbed boards. The
way to run it is to:

  1. Run the program as root (if you wish to get all possible info)
  2. Connect or disconnect the mbed devices when asked and hit enter

The program uses various Linux commands to achieve all this, by using low-level
information. That assures that we get information for even non-mbed devices.
'''

import re
import json, csv
import subprocess
import argparse

# uses the syntax of access()
TABLE_FORMAT = ':idVendor:0, :idProduct:0, :idVendor:1, :idProduct:1, :serial:1, :classes::1' 

parser = argparse.ArgumentParser(description='Mbed daemon.')
parser.add_argument('--output-json', dest='json', action='store_true',
	help='create a json file containg the devices\' information')
parser.set_defaults(log_function_calls=False)
parser.add_argument('--output-csv', dest='csv', action='store_true',
	help='create a csv file containg the devices\' information')
parser.set_defaults(log_function_calls=False)
args = parser.parse_args()

def is_running_as_root():
    p = subprocess.Popen(['whoami'], shell=False, stdout=subprocess.PIPE)
    return 'root' in p.stdout.read()

if not is_running_as_root():
    print('Needs to be run as root to get all information for USB devices')





# ------------------------------- USB info ------------------------------------

# Get information for a USB device
def get_dev_info(bus, dev):
    p = subprocess.Popen(['lsusb', '-s', '%s:%s' % (bus, dev), '-v'], shell=False, stdout=subprocess.PIPE)
    output = p.stdout.read()
    info = {}
    info['idVendor'] = re.search(r'idVendor.*(0x.{4}) (.*)\n', output).groups()
    info['idProduct'] = re.search(r'idProduct.*(0x.{4}) (.*)\n', output).groups()
    info['classes'] = list(set(re.findall(r'bInterfaceClass\s*([0-9]*)\s(.*)\n', output)))
    info['serial'] = re.search(r'iSerial\s*([0-9]*)\s(.*)\n', output).groups()
    return info

# This will give the nonhub USB devices currently connected
def get_usb_devices():
    p = subprocess.Popen(['lsusb'], shell=False, stdout=subprocess.PIPE)
    all_usb = re.findall(r'Bus ([0-9]{3}) Device ([0-9]{3})', p.stdout.read())
    devices = []
    for bus, dev in all_usb:
        dev = get_dev_info(bus, dev)
        classes = reduce(lambda x, y: x+y, dev['classes'])
        if not 'Hub' in classes:
            devices.append(dev)
    return devices





# ---------------------------- pyOCD support ----------------------------------







# ------------------------------ Formatting -----------------------------------


'''
This implementation is a fast way to access specific elements in a complex
nested structure. Keystring is a simple string that holds keys and indice
separated by colons. A colon without a key or index will end up expanding
through all elements depending on the context.

Example:
  access('0:0', lst)         # Is the same as lst[0][0]
  access('squares:0', lst)   # Is the same as lst['squares'][0]
  access('squares::0', lst)  # This will loop through lst['squares'] and for every item will give item[0]

As you might notice, this function is most useful when used with complex
nested structures.
'''
def access(keystring, container):
    key_sequence = keystring.rstrip(':').split(':')
    for i in range(len(key_sequence)):
        if key_sequence[i].isdigit():
            key_sequence[i] = int(key_sequence[i])
    def use_key(key, container):
        # case: empty str
        if key[0]=='':
            items = []
            if isinstance(container, dict):
                for k in container:
                    if len(key)>1:
                        items.append(use_key(key[1:], container[k]))
                    else:
                        items.append(container[k])
            elif hasattr(container, '__iter__'):
                for item in container:
                    items.append(use_key(key[1:], item))
            return items
        # case: index or key and still many keys
        elif len(key)>1:
            return use_key(key[1:], container[key[0]])
        # case: single index or key
        else:
            if (isinstance(container, dict) and key[0] in container) or\
                (hasattr(container, '__iter__') and key[0]<len(container)):
                return container[key[0]]
            else:
                return None
    return use_key(key_sequence, container)






def tablefy(keystring, struct, expand_lists_to_bool=False, flatten_lists=True):
    '''
    Keystring is a string using the same syntax used in the access() function.
    The keystring will be used to give rows as a list of lists. Notice that tablefy
    will work ONLY for iterables
    keystring            - multiple keystrings separated by comma. Check access()
                           documentation for more info
    expand_lists_to_bool - convert sublists in a row into booleans. This is
                           helpful if you want more compact output.
    flatten_lists        - if we get sublists, just flatten them out. In practice
                           if we don't flatten them out then the whole sublist
                           will be used as a one cell entry
    '''
    keystrings = [expr.strip() for expr in keystring.split(',')]
    header = keystrings[:]
    cols_expanded = []

    # Get columns first
    cols =  [ access(keystring_, struct) for keystring_ in keystrings ]
    for col in cols: assert len(col)==len(cols[0])

    # Expand columns with sublists to booleans
    if expand_lists_to_bool:
        for col in cols:
            if hasattr(col[0], '__iter__'):
                bool_names = list({ item for entry in col for item in entry })
                bool_names.sort()
                cols_expanded.append([cols.index(col), bool_names])
                for i in range(len(col)):
                    col[i] = map(lambda x: x in col[i], bool_names)

    # Update header with expansions and prettify
    for i, expansion in cols_expanded:
        header[i] = expansion
    prettyfied = []
    for h in header:
        if isinstance(h, str):
            lstripped = re.search(r'([a-zA-Z].*)', h).group(1)
            rstripped = re.sub(r':.*', '', lstripped)
            prettyfied.append(rstripped)
        else:
            prettyfied.append(h)
    header = prettyfied
    
    # Make rows
    rows = [header] + zip(*cols)
    
    # Flatten sublists
    if flatten_lists:
        flattened = []
        for row in rows:
            newrow = []
            for cell in row:
                if hasattr(cell, '__iter__'):
                    newrow.extend(cell)
                else:
                    newrow.append(cell)
            flattened.append(newrow)
        rows = flattened

    return rows





# --------------------------------- Main --------------------------------------

def diff_lists(l1, l2):
    if len(l1)>len(l2):
        return [i for i in l1 if not i in l2]
    else:
        return [i for i in l2 if not i in l1]

def save_as_csv(devices):
    fout = open('devices_info.csv', 'w')
    writer = csv.writer(fout, quoting=csv.QUOTE_MINIMAL)
    rows = tablefy(TABLE_FORMAT, devices, expand_lists_to_bool=True, flatten_lists=True)
    for row in rows:
         writer.writerow(row)
    fout.close()

def save_as_json(devices):
    fout = open('devices_info.json', 'w')
    fout.write(json.dumps(devices, indent=4, sort_keys=True))
    fout.close()

def print_devices(devices):
    table = tablefy(TABLE_FORMAT, devices, expand_lists_to_bool=True, flatten_lists=True)
    for row in table:
        print(row)

old_devices = get_usb_devices()
_ = raw_input('Connect or disconnect any boards that you want to examine and press enter\n')
devices = diff_lists(old_devices, get_usb_devices())

if args.json:
    save_as_json(devices)
if args.csv:
    save_as_csv(devices)


print_devices(devices)