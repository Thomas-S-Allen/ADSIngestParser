import datetime
import json
import os
import unittest

from adsingestschema import ads_schema_validator

from adsingestp.parsers import jats

# import logging
# proj_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "adsingestp"))
# logging.basicConfig(
#     format="%(levelname)s %(asctime)s %(message)s",
#     filename=os.path.join(proj_dir, "logs", "parser.log"),
#     level=logging.INFO,
#     force=True,
# )

TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


class TestJATS(unittest.TestCase):
    def setUp(self):
        stubdata_dir = os.path.join(os.path.dirname(__file__), "stubdata/")
        self.inputdir = os.path.join(stubdata_dir, "input")
        self.outputdir = os.path.join(stubdata_dir, "output")
        self.maxDiff = None

    def test_jats(self):

        filenames = [
            "jats_apj_859_2_101",
            "jats_mnras_493_1_141",
            "jats_aj_158_4_139",
            "jats_iop_ansnn_12_2_025001",
            "jats_aip_aipc_2470_040010",
            "jats_aip_amjph_90_286",
            "jats_phrvd_106_023001",
        ]
        for f in filenames:
            test_infile = os.path.join(self.inputdir, f + ".xml")
            test_outfile = os.path.join(self.outputdir, f + ".json")
            parser = jats.JATSParser()

            with open(test_infile, "rb") as fp:
                input_data = fp.read()

            with open(test_outfile, "rb") as fp:
                output_text = fp.read()
                output_data = json.loads(output_text)

            parsed = parser.parse(input_data)

            # make sure this is valid schema
            try:
                ads_schema_validator().validate(parsed)
            except Exception:
                self.fail("Schema validation failed")

            # this field won't match the test data, so check and then discard
            time_difference = (
                datetime.datetime.strptime(parsed["recordData"]["parsedTime"], TIMESTAMP_FMT)
                - datetime.datetime.utcnow()
            )
            self.assertTrue(abs(time_difference) < datetime.timedelta(seconds=10))
            parsed["recordData"]["parsedTime"] = ""

            self.assertEqual(parsed, output_data)

    def test_jats_lxml(self):
        # test parsing with BeautifulSoup parser='lxml'
        filenames = [
            "jats_iop_aj_162_1",
        ]
        for f in filenames:
            test_infile = os.path.join(self.inputdir, f + ".xml")
            test_outfile = os.path.join(self.outputdir, f + ".json")
            parser = jats.JATSParser()

            with open(test_infile, "rb") as fp:
                input_data = fp.read()

            with open(test_outfile, "rb") as fp:
                output_text = fp.read()
                output_data = json.loads(output_text)

            parsed = parser.parse(input_data, bsparser="lxml")

            # make sure this is valid schema
            try:
                ads_schema_validator().validate(parsed)
            except Exception:
                self.fail("Schema validation failed")

            # this field won't match the test data, so check and then discard
            time_difference = (
                datetime.datetime.strptime(parsed["recordData"]["parsedTime"], TIMESTAMP_FMT)
                - datetime.datetime.utcnow()
            )
            self.assertTrue(abs(time_difference) < datetime.timedelta(seconds=10))
            parsed["recordData"]["parsedTime"] = ""

            self.assertEqual(parsed, output_data)

    def test_jats_cite_context(self):
        filenames = [
            "jats_aj_158_4_139_fulltext",
        ]

        for f in filenames:
            test_infile = os.path.join(self.inputdir, f + ".xml")
            test_outfile = os.path.join(self.outputdir, f + ".json")
            parser = jats.JATSParser()

            with open(test_infile, "rb") as fp:
                input_data = fp.read()

            with open(test_outfile, "rb") as fp:
                output_text = fp.read()
                output_data = json.loads(output_text)

            cite_context = parser.citation_context(input_data)

            self.assertEqual(cite_context, output_data)
