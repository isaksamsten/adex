from app.adex import diag_disp, drug_disp
from app.adex.query import query_from_dict

import json
import logging

import sys
import numpy as np

import dt, rf

from autobahn.twisted.websocket import WebSocketServerProtocol

logger = logging.getLogger("adex")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr = logging.StreamHandler(sys.stdout)
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
hdlr.setLevel(logging.DEBUG)


class NumpyInt64(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.int64):
            return int(obj)  # or map(int, obj)
        return json.JSONEncoder.default(self, obj)


def format_population_query_response(population):
    return {
        'gender_distribution': population.gender_distribution.to_dict(),
        'age_distribution': population.age_distribution.reset_index().to_dict("records"),
        'drug_distribution': population.drug_distribution.order(ascending=False).reset_index().to_dict("rows"),
        'diagnos_distribution': population.diagnos_distribution.order(ascending=False).reset_index().to_dict("rows"),
        'total_no_patients': population.total_no_patients
    }


def server_protocol(frame):
    x = AdexServerProtocol
    x.frame = frame
    return x


# from sklearn import tree
import io


class AdexServerProtocol(WebSocketServerProtocol):
    def __init__(self):
        print "Hello world!!"
        self.case = None
        self.control = None
        self.request = None
        self.last_query = None
        self.last_case_query = None
        self.population = None

    def remote_build_dt(self):
        logger.info("building dt")
        if self.case and self.control:
            case = self.case.get_dataset(300)
            case.set_target(1)
            control = self.control.get_dataset(300)
            control.set_target(0)
            dataset = case.merge(control)

            print self.last_case_query
            dataset.drop_query(self.last_case_query)

            values = dataset.values

            x = values.drop("target", 1)
            y = values.target
            print y
            mdl = dt.fit(x.values, y.values, max_depth=8, feature_names=values.columns, target_names=["Yes", "No"])
            return {'dt': json.dumps(mdl)}

    def remote_build_rf(self):
        logger.info("building random forest")
        if self.case and self.control:
            case = self.case.get_dataset(300)
            case.set_target(1)
            control = self.control.get_dataset(300)
            control.set_target(0)
            dataset = case.merge(control)

            print self.last_case_query
            dataset.drop_query(self.last_case_query)

            values = dataset.values

            x = values.drop("target", 1)
            y = values.target
            print y
            importance = rf.fit(x, y, feature_names=values.columns, target_names=["Yes", "No"])
            return {'rf': json.dumps(importance)}

    def remote_population_get(self):
        logger.info("population_get for %s" % self.request.peer)
        if self.population:
            return format_population_query_response(self.population)
        else:
            return "no population"

    def remote_population_query(self, query):
        query = query_from_dict(query)
        logger.info("population_query for %s" % query)
        if self.last_query and self.last_query == query:
            return self.remote_population_get()

        self.last_query = query
        self.population = self.frame.query(query)
        return format_population_query_response(self.population)

    def remote_population_update(self, query):
        logger.info("population_update for %s" % query)
        query = query_from_dict(query)
        if self.last_query and self.last_query == query:
            return self.remote_population_get()

        if self.population:
            self.population = self.population.query(query)
        else:
            self.population = self.frame.query(query)
        return format_population_query_response(self.population)

    def remote_population_split(self, query):
        logger.info("split_population %s" % self.request.peer)
        query = query_from_dict(query)
        if not self.population:
            self.send_response("error", "no population set")
            return

        self.last_case_query = query
        (self.case, self.control) = self.population.split(query)

        return {
            "case": format_population_query_response(self.case),
            "control": format_population_query_response(self.control)
        }

    def remote_case_control_remove(self):
        self.case = None
        self.control = None

    def remote_population_remove(self):
        self.population = None
        self.last_query = None
        self.case = None
        self.control = None

    def remote_population_disp(self, code):
        logger.info("calculating disp for %s" % code)
        if not self.population:
            self.send_response("error", "no population set")
            return
        pairs = diag_disp.code_pairs(self.population, code)
        d = pairs.disproportionality()
        print d.to_dict()
        return d.reset_index().to_dict("record")

    def remote_population_drug_disp(self, code):
        logger.info("calculating drug_disp for %s" % code)
        if not self.population:
            self.send_response("error", "no population set")
            return
        pairs = drug_disp.code_pairs(self.population, code)
        d = pairs.disproportionality()
        print d.to_dict()
        return d.reset_index().to_dict("record")

    def onConnect(self, request):
        self.request = request
        logger.debug("Client connecting: %s" % request.peer)

    def onOpen(self):
        self.population = None
        self.last_query = None
        self.case = None
        self.control = None

    def send_response(self, method, args=None, cls=None):
        if args is not None:
            self.sendMessage(json.dumps({"method": method, "args": args}, cls=cls).encode('utf8'))
        else:
            self.sendMessage(json.dumps({"method": method}, cls=cls).encode('utf8'))

    def onMessage(self, payload, isBinary):
        if isBinary:
            self.send_response("error", "isBinary == true (should be false)")

        req = json.loads(payload.decode('utf8'))
        if not "method" in req:
            self.send_response("error", "no method specified")

        try:
            method = getattr(self, "remote_" + req["method"])
            if "args" in req:
                result = method(*req["args"])
            else:
                result = method()

            self.send_response(req["method"], result, cls=NumpyInt64)
        except Exception as e:
            logger.exception(e)
            self.sendMessage(json.dumps({"method": "error", "args": str(e)}).encode('utf8'))

    def onClose(self, was_clean, code, reason):
        print("WebSocket connection closed: {}".format(reason))














