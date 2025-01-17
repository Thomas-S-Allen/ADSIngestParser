import logging
import re

from adsingestp.ingest_exceptions import XmlLoadException
from adsingestp.parsers.base import BaseBeautifulSoupParser

logger = logging.getLogger(__name__)

orcid_format = re.compile(r"(\d{4}-){3}\d{3}(\d|X)")


class WileyParser(BaseBeautifulSoupParser):
    def __init__(self):
        self.base_metadata = {}
        self.pubmeta_prod = None
        self.pubmeta_part = None
        self.pubmeta_unit = None
        self.content_meta = None

    def _parse_ids(self):
        self.base_metadata["ids"] = {}

        self.base_metadata["issn"] = []
        for i in self.pubmeta_prod.find_all("issn"):
            self.base_metadata["issn"].append((i["type"], i.get_text()))

        if self.pubmeta_unit.find("doi"):
            self.base_metadata["ids"]["doi"] = self.pubmeta_unit.find("doi").get_text()

        self.base_metadata["ids"]["pub-id"] = []
        for i in self.pubmeta_unit.find_all("id"):
            if i["type"] not in ["society", "eLocator"]:
                self.base_metadata["ids"]["pub-id"].append(
                    {"attribute": i["type"], "Identifier": i["value"]}
                )

    def _parse_pub(self):
        for t in self.pubmeta_prod.find_all("title"):
            if t["type"] == "main":
                self.base_metadata["publication"] = t.get_text()

        for n in self.pubmeta_part.find_all("numbering"):
            if n["type"] == "journalVolume":
                self.base_metadata["volume"] = n.get_text()
            elif n["type"] == "journalIssue":
                self.base_metadata["issue"] = n.get_text()

    def _parse_page(self):
        page_first = None
        for n in self.pubmeta_unit.find_all("numbering"):
            if n["type"] == "pageFirst":
                page_first = n.get_text()
            elif n["type"] == "pageLast":
                if n.get_text() not in ["n/a", "no"]:
                    self.base_metadata["page_last"] = n.get_text()
        if not page_first:
            for i in self.pubmeta_unit.find_all("id"):
                if i["type"] == "society":
                    page_first = i.get_text()
                if i["type"] == "eLocator":
                    # TODO check w/ curators - the last 5 is what the perl was doing, but should we keep the whole thing?
                    self.base_metadata["electronic_id"] = i.get_text()[-5:]

        if page_first in ["n/a", "no"]:
            page_first = None

        if page_first:
            self.base_metadata["page_first"] = page_first

        if self.pubmeta_unit.find("countGroup") and self.pubmeta_unit.find("countGroup").find(
            "count"
        ):
            if self.pubmeta_unit.find("countGroup").find("count")["type"] == "pageTotal":
                self.base_metadata["numpages"] = self.pubmeta_unit.find("countGroup").find(
                    "count"
                )["number"]

    def _parse_pubdate(self):
        if self.pubmeta_part.find("coverDate"):
            pubdate = self.pubmeta_part.find("coverDate")["startDate"].split("-")
            year = pubdate[0]
            if len(pubdate) > 1:
                month = pubdate[1]
            else:
                month = "00"
            if len(pubdate) > 2:
                day = pubdate[2]
            else:
                day = "00"
            self.base_metadata["pubdate_print"] = year + "-" + month + "-" + day

        found = False
        for d in self.pubmeta_unit.find_all("event"):
            if d["type"] == "firstOnline":
                # this is the top choice, end if this is found
                self.base_metadata["pubdate_electronic"] = d["date"]
                found = True
                break
            elif d["type"] == "publishedOnlineFinalForm":
                # second choice, keep searching
                self.base_metadata["pubdate_electronic"] = d["date"]
                found = True
            elif d["type"] == "publishedOnlineAccepted" and not found:
                # third choice, only take if nothing else has been found yet
                self.base_metadata["pubdate_electronic"] = d["date"]

    def _parse_edhistory(self):
        # key: xml tag, value: self.base_metadata key
        dates_trans = {
            "manuscriptRevised": "edhist_rev",
            "manuscriptReceived": "edhist_rec",
            "manuscriptAccepted": "edhist_acc",
        }
        for d in self.pubmeta_unit.find_all("event"):
            if d["type"] in dates_trans.keys():
                date_key = d["type"]
                if date_key == "manuscriptAccepted":
                    # this only accepts a single date, the other two accept a list
                    date_out = d["date"]
                else:
                    date_out = [d["date"]]
                self.base_metadata[dates_trans[date_key]] = date_out

    def _parse_title_abstract(self):
        if self.content_meta.find("titleGroup"):
            for t in self.content_meta.find("titleGroup").find_all("title"):
                if t["type"] == "main":
                    self.base_metadata["title"] = t.get_text()

        # TODO subtitles?

        if self.content_meta.find("abstractGroup"):
            for a in self.content_meta.find("abstractGroup").find_all("abstract"):
                if a["type"] == "main":
                    self.base_metadata["abstract"] = self._clean_output(a.get_text())

    def _parse_copyright(self):
        if self.pubmeta_unit.find("copyright"):
            self.base_metadata["copyright"] = self.pubmeta_unit.find("copyright").get_text()

    def _parse_authors(self):
        aff_dict = {}
        for a in self.content_meta.find_all("affiliation"):
            # build affiliations cross-reference dict
            label = a["xml:id"]
            value = a.get_text(separator=", ", strip=True)
            aff_dict[label] = value

        author_list = []
        for c in self.content_meta.find_all("creator"):
            author_tmp = {}
            if c.find("givenNames"):
                author_tmp["given"] = c.find("givenNames").get_text()
            if c.find("familyName"):
                author_tmp["surname"] = c.find("familyName").get_text()
            for id in c.find_all("id"):
                if id["type"] == "orcid":
                    orcid = id["value"]
                    # ORCID IDs sometimes have the URL prepended - remove it
                    if orcid_format.search(orcid):
                        author_tmp["orcid"] = orcid_format.search(orcid).group(0)
            if c.find("email"):
                author_tmp["email"] = c.find("email").get_text()
            if c.has_attr("affiliationRef"):
                affs_raw = c["affiliationRef"]
                affs_raw_arr = affs_raw.split()
                affs = []
                xaffs = []
                for a in affs_raw_arr:
                    if aff_dict.get(a):
                        akey = a
                    elif aff_dict.get(a.replace("#", "")):
                        akey = a.replace("#", "")
                    xaffs.append(akey)
                    affs.append(aff_dict[akey])
                author_tmp["aff"] = affs
                author_tmp["xaff"] = xaffs
            author_list.append(author_tmp)

        if author_list:
            self.base_metadata["authors"] = author_list

    def _parse_keywords(self):
        keywords = []
        for k in self.content_meta.find_all("keyword"):
            keywords.append({"system": "Wiley", "string": k.get_text()})

    def _parse_references(self):
        references = []
        if self.bib:
            for ref in self.bib.find_all("citation"):
                # output raw XML for reference service to parse later
                ref_xml = str(ref.extract()).replace("\n", " ").replace("\xa0", " ")
                references.append(ref_xml)

            self.base_metadata["references"] = references

    def parse(self, text):
        """
        Parse Wiley XML into standard JSON format
        :param text: string, contents of XML file
        :return: parsed file contents in JSON format
        """
        try:
            d = self.bsstrtodict(text, parser="lxml-xml")
        except Exception as err:
            raise XmlLoadException(err)

        for p in d.find_all("publicationMeta"):
            if p["level"] == "product":
                self.pubmeta_prod = p
            elif p["level"] == "part":
                self.pubmeta_part = p
            elif p["level"] == "unit":
                self.pubmeta_unit = p

        self.content_meta = d.find("contentMeta")
        self.bib = d.find("bibliography")

        self._parse_ids()
        self._parse_pub()
        self._parse_page()
        self._parse_pubdate()
        self._parse_edhistory()
        self._parse_title_abstract()
        self._parse_copyright()
        self._parse_authors()
        self._parse_keywords()
        self._parse_references()

        output = self.format(self.base_metadata, format="OtherXML")

        return output
