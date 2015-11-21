#!/usr/bin/env python3

import errno
import json
import os
import shutil
import ssl
import sqlite3
import sys
import threading

from collections import OrderedDict, defaultdict
from flask import Flask, make_response, send_file
from flask_restful import reqparse, abort, Api, Resource
from time import gmtime, strftime
from locale import getlocale
from subprocess import Popen, PIPE

# TODO
#      - TLS
#      - Assessments
app = Flask(__name__, static_url_path=os.path.dirname(os.path.abspath(__file__)))
api = Api(app)

parser = reqparse.RequestParser()
# for /tools
parser.add_argument('search')
# for /assessments/jobs and /tools/jobs
parser.add_argument('id')
parser.add_argument('assessment')
parser.add_argument('tool')
parser.add_argument('target')
parser.add_argument('target_name')
parser.add_argument('protocol')
parser.add_argument('port_number')
parser.add_argument('user')
parser.add_argument('password')
parser.add_argument('user_file')
parser.add_argument('password_file')

class RunThreads (threading.Thread):
    def __init__(self, tool, job, context):
        threading.Thread.__init__(self)
        self.tool_stdout = ''
        self.tool_sterr = ''
        self.tool = tool
        self.job = job
        self.context = context

    def execute_tool(self, job, context):
        # Always check any tools provided by
        # community members
        print("Running")
        proc = Popen(self.tool['execute_string'], stdout=PIPE, stderr=PIPE, shell=True)

        decode_locale = lambda s: s.decode(getlocale()[1])
        self.tool_stdout, self.tool_stderr = map(decode_locale, proc.communicate())

        # Callback / pause from here
        return_code = proc.returncode
        # Zip resulting directory
        zip_file = None
        if return_code == 0:
            zip_file = os.path.dirname(os.path.abspath(__file__)) + \
                "/" + job['target_name'] + '_' + str(job['id'])
            shutil.make_archive(zip_file, 'zip', job['output_dir'])

        # Update completed and return_code field in db
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        cur = con.cursor()
        if context == 'tool':
            cur.execute("UPDATE tool_jobs SET executed = 1, return_code = ?, zip_file = ? WHERE id = ?",(str(return_code),str(zip_file),str(job['id'])))
            con.commit()
        if context == 'assessment':
            # Pull and check for 0
            cur.execute("SELECT return_code FROM assessment_jobs WHERE id = ? AND return_code == 0",(str(job['id'])))
            data = cur.fetchall()
            if len(data) == 0 or data[0][0] == 0:
                cur.execute("UPDATE assessment_jobs SET executed = 1, return_code = ?, zip_file = ? WHERE id = ?",(str(return_code),str(zip_file),str(job['id'])))
                con.commit()

        # Close connection
        if con:
            con.close()

    def run(self):
        self.execute_tool(self.job, self.context)

class Pong(Resource):
    def get(self):
        return { 'message':'pong' }

class Assessments(Resource):
    # Get assessments
    def get(self):
        args = parser.parse_args()
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # If /assessments?search=xxx not specified then SELECT *
        if args['search'] != None:
            cur.execute("SELECT * FROM assessments WHERE name LIKE ? OR description LIKE ?",('%' + args['search'] + '%','%' + args['search'] + '%'))
        else:
            cur.execute("SELECT * FROM assessments")
        data = dict(result=[dict(r) for r in cur.fetchall()])

        # Add tools to assessment
        for i, assessment in enumerate(data['result']):
            cur.execute("SELECT tool FROM assessment_tools WHERE assessment = ?",(str(i),))
            tool_ids = dict(result=[dict(r) for r in cur.fetchall()])
            assessment['tools'] = tool_ids['result']

        # Close connection
        if con:
            con.close()
        return data

    # Submit a new tool
    def post(self):
        args = parser.parse_args()
        return args

class Tools(Resource):
    # Get tools
    def get(self):
        args = parser.parse_args()
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # If /tools?search=xxx not specified then SELECT *
        if args['search'] != None:
            cur.execute("SELECT * FROM tools WHERE name LIKE ? OR description LIKE ?",('%' + args['search'] + '%','%' + args['search'] + '%'))
        else:
            cur.execute("SELECT * FROM tools")
        data = dict(result=[dict(r) for r in cur.fetchall()])

        # Close connection
        if con:
            con.close()
        return data

    # Submit a new tool
    def post(self):
        args = parser.parse_args()
        return args

class ToolsJobs(Resource):
    # List jobs
    def get (self):
        args = parser.parse_args()
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # If /jobs?search=xxx not specified then SELECT *
        if args['search'] != None:
           cur.execute("SELECT * FROM tool_jobs WHERE tool LIKE ? OR target LIKE ? OR target_name LIKE ? OR protocol LIKE ? OR port_number LIKE ? OR user like ? OR password LIKE ? OR user_file LIKE ? OR password_file LIKE ?",('%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%'))
        else:
           cur.execute("SELECT * FROM tool_jobs")
        data = dict(result=[dict(r) for r in cur.fetchall()])

        # Close connection
        if con:
            con.close()

        return data

    # Submit new job
    def post(self):
        args = parser.parse_args()
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        cur = con.cursor()

        # curl -i --data "tool=1&target=localhost&target_name=target_name&protocol=https&port_number=1337&user=a_user&password=a_password&user_file=/user/file&password_file=/password/file" http://127.0.0.1:5000/jobs
        cur.execute("INSERT INTO tool_jobs(tool,target,target_name,protocol,port_number,user,password,user_file,password_file) VALUES(?,?,?,?,?,?,?,?,?)",(args['tool'],args['target'],args['target_name'],args['protocol'],args['port_number'],args['user'],args['password'],args['user_file'],args['password_file']))
        data = cur.lastrowid
        con.commit()

        # Close connection
        if con:
            con.close()

        return { 'id':data }, 201

# List individual jobs
class ToolsJobsId(Resource):
    def get(self, job_id):
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute("SELECT * FROM tool_jobs WHERE id = ?",(job_id,))
        data = dict(result=[dict(r) for r in cur.fetchall()])

        # Close connection
        if con:
            con.close()

        return data

# Execute job
class ToolsJobsIdExecute(Resource):
    def post(self):
        # Process placeholders
        tool = {}
        job = {}
        args = parser.parse_args()
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # Get job id columns
        cur.execute("SELECT * FROM tool_jobs WHERE id = ?",(args['id'],))
        job_data = dict(result=[dict(r) for r in cur.fetchall()])

        # Index is now tied to database schema, yuck
        print(args['id'])
        job = job_data['result'][0]
        # TODO Allow set in config file
        job['tools_directory'] = "/root/tools"
        job['date'] = strftime("%Y%m%d_%H%M%S%z")
        job['output_dir'] = os.path.dirname(os.path.abspath(__file__)) + \
                                '/' + strftime("%Y%m%d") + \
                                "_autopwn_" + \
                                job_data['result'][0]['target_name']
        try:
            os.makedirs(job['output_dir'])
        except OSError as e:
            if e.errno == errno.EEXIST:
                return {'message':'Directory exists'}, 500

        tool['id'] = job['tool']
        # Get dependencies
        cur.execute("SELECT dependency from dependencies WHERE tool = ?",(tool['id'],))
        dependency = dict(result=[dict(r) for r in cur.fetchall()])

        # Get tool execute string
        cur.execute("SELECT * FROM tools WHERE id = ?",(tool['id'],))
        tool_data = dict(result=[dict(r) for r in cur.fetchall()])
        tool = tool_data['result'][0]

        # Close connection
        if con:
            con.close()

        ddict_options = defaultdict(lambda:'')
        for option in job:
            ddict_options[option] = job[option]

        tool['execute_string'] = tool['execute_string'].format(**ddict_options)
        print(tool['execute_string'])

        thread = []
        # Tool string generated, execute
        thread.append(RunThreads(tool,job,'tool'))
        # If main process dies, everything else *SHOULD* as well
        thread[-1].daemon = True
        # Start threads
        thread[-1].start()

        return {'message':'Tool executed'}, 201

class AssessmentsJobs(Resource):
    # List jobs
    def get (self):
        args = parser.parse_args()
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # If /assessments/jobs?search=xxx not specified then SELECT *
        if args['search'] != None:
           cur.execute("SELECT * FROM assessment_jobs WHERE tool LIKE ? OR target LIKE ? OR target_name LIKE ? OR protocol LIKE ? OR port_number LIKE ? OR user like ? OR password LIKE ? OR user_file LIKE ? OR password_file LIKE ?",('%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%','%' + args['search'] + '%'))
        else:
           cur.execute("SELECT * FROM assessment_jobs")
        data = dict(result=[dict(r) for r in cur.fetchall()])

        # Close connection
        if con:
            con.close()

        return data

    # Submit new job
    def post(self):
        args = parser.parse_args()
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        cur = con.cursor()

        # curl -i --data "assessment=1&target=localhost&target_name=target_name&protocol=https&port_number=1337&user=a_user&password=a_password&user_file=/user/file&password_file=/password/file" http://127.0.0.1:5000/assessments/jobs
        cur.execute("INSERT INTO assessment_jobs(assessment,target,target_name,protocol,port_number,user,password,user_file,password_file) VALUES(?,?,?,?,?,?,?,?,?)",(args['assessment'],args['target'],args['target_name'],args['protocol'],args['port_number'],args['user'],args['password'],args['user_file'],args['password_file']))
        data = cur.lastrowid
        con.commit()

        # Close connection
        if con:
            con.close()

        return { 'id':data }, 201

# List individual jobs
class AssessmentsJobsId(Resource):
    def get(self, job_id):
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute("SELECT * FROM assessment_jobs WHERE id = ?",(job_id,))
        data = dict(result=[dict(r) for r in cur.fetchall()])

        # Close connection
        if con:
            con.close()

        return data

# Execute job
class AssessmentsJobsIdExecute(Resource):
    def post(self):
        # Process placeholders
        assessment = {}
        job = {}
        args = parser.parse_args()
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # Get job id columns
        cur.execute("SELECT * FROM assessment_jobs WHERE id = ?",(args['id'],))
        job_data = dict(result=[dict(r) for r in cur.fetchall()])

        # Index is now tied to database schema, yuck
        job = job_data['result'][0]
        # TODO Allow set in config file
        job['tools_directory'] = "/root/tools"
        job['date'] = strftime("%Y%m%d_%H%M%S%z")
        job['output_dir'] = os.path.dirname(os.path.abspath(__file__)) + \
                                '/' + strftime("%Y%m%d") + \
                                "_autopwn_" + \
                                job_data['result'][0]['target_name']
        # TODO Uncomment
        try:
            os.makedirs(job['output_dir'])
        except OSError as e:
            if e.errno == errno.EEXIST:
                return {'message':'Directory exists'}, 500

        assessment['id'] = job['assessment']
        cur.execute("SELECT tool FROM assessment_tools WHERE assessment = ?",(str(assessment['id'])))
        tool_ids = dict(result=[dict(r) for r in cur.fetchall()])
        assessment['tools'] = tool_ids['result']

        for i, data in enumerate(assessment['tools']):
            # Get dependencies
            cur.execute("SELECT dependency from dependencies WHERE tool = ?",(data['tool'],))
            dependency = dict(result=[dict(r) for r in cur.fetchall()])

            # Get tool execute string
            cur.execute("SELECT * FROM tools WHERE id = ?",(data['tool'],))
            tool_data = dict(result=[dict(r) for r in cur.fetchall()])
            tool = tool_data['result'][0]

            ddict_options = defaultdict(lambda:'')
            for option in job:
                ddict_options[option] = job[option]

            tool['execute_string'] = tool['execute_string'].format(**ddict_options)
            print(tool['execute_string'])

            thread = []
            # Tool string generated, execute
            thread.append(RunThreads(tool,job,'assessment'))
            # If main process dies, everything else *SHOULD* as well
            thread[-1].daemon = True
            # Start threads
            thread[-1].start()

        # Close connection
        if con:
            con.close()

        return {'message':'Assessment executed'}, 201

class Dependencies(Resource):
    def get(self):
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute("SELECT * FROM dependency_names")
        data = dict(result=[dict(r) for r in cur.fetchall()])

        # Close connection
        if con:
            con.close()

        return data

class Options(Resource):
    def get(self):
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute("SELECT * FROM options")
        data = dict(result=[dict(r) for r in cur.fetchall()])

        # Close connection
        if con:
            con.close()

        return data

# Retrieve options for tool
class OptionsId(Resource):
    def get(self, tool_id):
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute("SELECT option, required FROM tool_options WHERE tool = ?",(tool_id,))
        data = dict(result=[dict(r) for r in cur.fetchall()])

        # Close connection
        if con:
            con.close()

        return data

class AssessmentsExports(Resource):
    def get(self):
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute("SELECT id, zip_file FROM assessment_jobs")
        data = dict(result=[dict(r) for r in cur.fetchall()])
        print(data)

        # Close connection
        if con:
            con.close()

        return data

# Retrieve output for job id
class AssessmentsExportsId(Resource):
    def get(self, job_id):
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute("SELECT zip_file FROM assessment_jobs WHERE id = ?",(job_id,))
        data = dict(result=[dict(r) for r in cur.fetchall()])
        zip_file = data['result'][0]['zip_file'] + '.zip'

        # Close connection
        if con:
            con.close()

        return send_file(zip_file, as_attachment=True)


class ToolsExports(Resource):
    def get(self):
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute("SELECT id, zip_file FROM tool_jobs")
        data = dict(result=[dict(r) for r in cur.fetchall()])
        print(data)

        # Close connection
        if con:
            con.close()

        return data

# Retrieve output for job id
class ToolsExportsId(Resource):
    def get(self, job_id):
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute("SELECT zip_file FROM tool_jobs WHERE id = ?",(job_id,))
        data = dict(result=[dict(r) for r in cur.fetchall()])
        zip_file = data['result'][0]['zip_file'] + '.zip'

        # Close connection
        if con:
            con.close()

        return send_file(zip_file, as_attachment=True)

# Retrieve dependencies for tool
class DependenciesId(Resource):
    def get(self, tool_id):
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/assets.db')
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute("SELECT dependency FROM dependencies WHERE tool = ?",(tool_id,))
        data = dict(result=[dict(r) for r in cur.fetchall()])

        # Close connection
        if con:
            con.close()

        return data

# Pong!
# curl -i http://127.0.0.1:5000/ping
api.add_resource(Pong, '/ping')
# Fetch all tools
# curl -i http://127.0.0.1:5000/tools
api.add_resource(Tools, '/tools')
# Fetch all assessments
# curl -i http://127.0.0.1:5000/assessments
api.add_resource(Assessments, '/assessments')

# Fetch all assessment jobs
# curl -i http://127.0.0.1:5000/assessments/jobs
api.add_resource(AssessmentsJobs, '/assessments/jobs')
# Fetch assessment id
# curl -i http://127.0.0.1:5000/assessments/jobs/1
api.add_resource(AssessmentsJobsId, '/assessments/jobs/<job_id>')
# Execute assesment job id
# curl -i --data "id=1" http://127.0.0.1:5000/assessments/jobs/execute
api.add_resource(AssessmentsJobsIdExecute, '/assessments/jobs/execute')

# Fetch all tool jobs
# curl -i http://127.0.0.1:5000/jobs
api.add_resource(ToolsJobs, '/tools/jobs')
# Fetch tool job id
# curl -i http://127.0.0.1:5000/jobs/1
api.add_resource(ToolsJobsId, '/tools/jobs/<job_id>')
# Execute tool job id
# curl -i --data "id=1" http://127.0.0.1:5000/jobs/execute
api.add_resource(ToolsJobsIdExecute, '/tools/jobs/execute')

# Fetch all dependencies
# curl -i http://127.0.0.1:5000/dependencies
api.add_resource(Dependencies, '/dependencies')
# Fetch all dependencies for tool id
api.add_resource(DependenciesId, '/dependencies/<tool_id>')
# TODO Review (/tools/options? /assessment/options?)
# Fetch all options
# curl -i http://127.0.0.1:5000/options
api.add_resource(Options, '/options')
# Fetch all options for tool id
# curl -i http://127.0.0.1:5000/options/1
api.add_resource(OptionsId, '/options/<tool_id>')

# Fetch all assessment outputs
# curl -i http://127.0.0.1:5000/exports
api.add_resource(AssessmentsExports, '/assessments/jobs/exports')
# Fetch assessment output from job id
# curl -i http://127.0.0.1:5000/exports/1
api.add_resource(AssessmentsExportsId, '/assessments/jobs/exports/<job_id>')

# Fetch all tool outputs
# curl -i http://127.0.0.1:5000/exports
api.add_resource(ToolsExports, '/tools/jobs/exports')
# Fetch tool output from job id
# curl -i http://127.0.0.1:5000/exports/1
api.add_resource(ToolsExportsId, '/tools/jobs/exports/<job_id>')

def main():
    print(os.path.dirname(os.path.abspath(__file__)))
    #context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    #context.load_cert_chain('yourserver.crt', 'yourserver.key')

    if os.path.isfile('/.dockerinit'):
        print("Running in docker")
        #app.run(host='0.0.0.0', debug=True,threaded=True,ssl_context=context)
        app.run(host='0.0.0.0', debug=True,threaded=True)
    else:
        #app.run(debug=True,threaded=True,ssl_context=context)
        app.run(debug=True,threaded=True)

if __name__ == '__main__':
    main()
