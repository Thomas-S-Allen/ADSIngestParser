import logging

from adsingestp import utils
from adsingestp.ingest_exceptions import (
    MissingAuthorsException,
    MissingTitleException,
    NoSchemaException,
    WrongSchemaException,
    XmlLoadException,
)
from adsingestp.parsers.base import BaseBeautifulSoupParser, IngestBase

logger = logging.getLogger(__name__)


class MultiArxivParser(IngestBase):
    start_re = r"<record(?!-)[^>]*>"
    end_re = r"</record(?!-)[^>]*>"

    def parse(self, text, header=False):
        """
        Separate multi-record arXiv XML document into individual XML documents

        :param text: string, input XML text from a multi-record XML document
        :param header: boolean (default: False), set to True to preserve overall
            document header/footer for each separate record's document
        :return: list, each item is the XML of a separate arXiv document
        """
        output_chunks = []
        for chunk in self.get_chunks(text, self.start_re, self.end_re, head_foot=header):
            output_chunks.append(chunk.strip())

        return output_chunks


class ArxivParser(BaseBeautifulSoupParser):
    # Dublin Core parser for arXiv

    DUBCORE_SCHEMA = ["http://www.openarchives.org/OAI/2.0/oai_dc/"]

    author_collaborations_params = {
        "keywords": ["group", "team", "collaboration"],
        "remove_the": False,
        "fix_arXiv_mixed_collaboration_string": True,
    }

    def __init__(self):
        self.base_metadata = {}
        self.input_header = None
        self.input_metadata = None

    def _parse_ids(self):
        if self.input_header.find("identifier"):
            ids = self.input_header.find("identifier").get_text()
            id_array = ids.split(":")
            arxiv_id = id_array[-1]

            # TODO what should the key on this actually be?
            self.base_metadata["publication"] = "eprint arXiv:" + arxiv_id

            self.base_metadata["ids"] = {"preprint": {}}

            self.base_metadata["ids"]["preprint"]["source"] = "arXiv"
            self.base_metadata["ids"]["preprint"]["id"] = arxiv_id

        dc_ids = self.input_metadata.find_all("dc:identifier")
        for d in dc_ids:
            d_text = d.get_text()
            if "doi:" in d_text:
                self.base_metadata["ids"]["doi"] = d_text.replace("doi:", "")

    def _parse_title(self):
        title_array = self.input_metadata.find_all("dc:title")
        if title_array:
            title_array_text = [i.get_text() for i in title_array]
            if len(title_array) == 1:
                self.base_metadata["title"] = self._clean_output(title_array_text[0])
            else:
                self.base_metadata["title"] = self._clean_output(": ".join(title_array_text))
        else:
            raise MissingTitleException("No title found")

    def _parse_author(self):
        authors_out = []
        name_parser = utils.AuthorNames()

        author_array = self.input_metadata.find_all("dc:creator")
        for a in author_array:
            a = a.get_text()
            parsed_name_list = name_parser.parse(
                a, collaborations_params=self.author_collaborations_params
            )
            for name in parsed_name_list:
                authors_out.append(name)

        if not authors_out:
            raise MissingAuthorsException("No contributors found for")

        self.base_metadata["authors"] = authors_out

    def _parse_pubdate(self):
        if self.input_metadata.find("dc:date"):
            self.base_metadata["pubdate_electronic"] = self.input_metadata.find(
                "dc:date"
            ).get_text()

    def _parse_abstract(self):
        desc_array = self.input_metadata.find_all("dc:description")
        # for arXiv.org, only 'dc:description'[0] is the abstract, the rest are comments
        if desc_array:
            self.base_metadata["abstract"] = self._clean_output(desc_array.pop(0).get_text())

        if desc_array:
            comments_out = []
            for d in desc_array:
                comments_out.append({"origin": "arxiv", "text": self._clean_output(d.get_text())})

            self.base_metadata["comments"] = comments_out

    def _parse_keywords(self):
        keywords_array = self.input_metadata.find_all("dc:subject")

        if keywords_array:
            keywords_out = []
            for k in keywords_array:
                keywords_out.append({"system": "arxiv", "string": k.get_text()})
            self.base_metadata["keywords"] = keywords_out

    def parse(self, text):
        """
        Parse arXiv XML into standard JSON format
        :param text: string, contents of XML file
        :return: parsed file contents in JSON format
        """
        try:
            d = self.bsstrtodict(text, parser="lxml-xml")
        except Exception as err:
            raise XmlLoadException(err)

        if d.find("record"):
            self.input_header = d.find("record").find("header")
        if d.find("record") and d.find("record").find("metadata"):
            self.input_metadata = d.find("record").find("metadata").find("oai_dc:dc")

        schema_spec = self.input_metadata.get("xmlns:oai_dc", "")
        if not schema_spec:
            raise NoSchemaException("Unknown record schema.")
        elif schema_spec not in self.DUBCORE_SCHEMA:
            raise WrongSchemaException("Wrong schema.")

        self._parse_ids()
        self._parse_title()
        self._parse_author()
        self._parse_pubdate()
        self._parse_abstract()
        self._parse_keywords()

        self.base_metadata = self._entity_convert(self.base_metadata)

        output = self.format(self.base_metadata, format="OtherXML")

        return output
