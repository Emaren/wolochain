"""C01 merged-PR source-CI evidence: historical GitHub association fallback.

Hermetic exact PR and GitHub ancestry fixtures. No secrets, network,
wallet, custody runtime, receipt writes or funded authority.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "wolo_artifact", ROOT/"scripts"/"settlement-artifact.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SOURCE=m.C01_ENROLLED_SOURCE
BUILDER="e"*40
ORIGINAL_HEAD="d"*40
MERGED="c1e14d7e82abe939675b161d34407fce3f7292c6"
REPO="https://api.github.com/repos/Emaren/wolochain"

class Read:
    def __init__(self,results):
        self.results=results
        self.calls=[]
    def __call__(self,url,*,expected_type=dict):
        self.calls.append(url)
        if url not in self.results:
            raise m.ArtifactError("SOURCE_CI_HOLD missing authenticated GitHub page")
        value=self.results[url]
        if type(value) is not expected_type:
            raise m.ArtifactError("SOURCE_CI_HOLD wrong returned document shape")
        return copy.deepcopy(value)

class HistoricalProofTests(unittest.TestCase):
    def setUp(self):
        repo={"id":m.C01_SOURCE_REPOSITORY_ID,"url":REPO,"name":"wolochain"}
        self.pr={
            "number":124,"id":m.C01_SOURCE_PULL_REQUEST_ID,
            "url":REPO+"/pulls/124","commits":3,
            "state":"closed","merged_at":"2026-11-04T01:14:54Z",
            "merge_commit_sha":MERGED,
            "head":{"ref":m.C01_SOURCE_HEAD_REF,"sha":ORIGINAL_HEAD,
                    "repo":repo.copy()},
            "base":{"ref":m.C01_SOURCE_BASE_REF,"sha":m.C01_SOURCE_BASE_COMMIT,
                    "repo":repo.copy()},
        }
        self.commits=[{"sha":SOURCE},{"sha":"c"*40},{"sha":ORIGINAL_HEAD}]
        self.run={
            "pull_requests":[],
            "repository":{"id":m.C01_SOURCE_REPOSITORY_ID,"full_name":m.EXPECTED_REPOSITORY},
            "head_repository":{"id":m.C01_SOURCE_REPOSITORY_ID,"full_name":m.EXPECTED_REPOSITORY},
            "head_branch":m.C01_SOURCE_HEAD_REF,
        }
        self.documents={
            REPO+"/pulls/124":self.pr,
            REPO+"/pulls/124/commits?per_page=100":self.commits,
        }

    def review(self):
        return m._c01_authenticated_merged_pr(self.run,SOURCE,Read(self.documents))

    def test_exact_merged_pr_and_source_membership_accepted(self):
        r=self.review()
        self.assertEqual(r["identity"]["number"],124)
        self.assertEqual(r["identity"]["head_sha"],ORIGINAL_HEAD)
        self.assertEqual(r["identity"]["qualified_source_sha"],SOURCE)
        self.assertEqual(r["merge_sha"],MERGED)
        self.assertEqual(r["commit_count"],3)

    def test_empty_association_only_not_absent_or_nonempty(self):
        for variant in (None,[],[{"number":124}],["fake"]):
            with self.subTest(variant=variant):
                q=copy.deepcopy(self.run)
                if variant is None:q.pop("pull_requests")
                else:q["pull_requests"]=variant
                if variant == []:
                    self.assertEqual(m._c01_authenticated_merged_pr(
                        q,SOURCE,Read(self.documents))["merge_sha"],MERGED)
                else:
                    with self.assertRaises(m.ArtifactError):
                        m._c01_authenticated_merged_pr(q,SOURCE,Read(self.documents))

    def test_reject_fake_merged_pr_or_malformed_merger_sha(self):
        for field,value in (("state","open"),("merged_at",None),
                            ("merge_commit_sha","A"*40),("merge_commit_sha","bad")):
            with self.subTest(field=field,value=value):
                old=self.pr[field]
                self.pr[field]=value
                with self.assertRaises(m.ArtifactError):self.review()
                self.pr[field]=old

    def test_reject_pr_number_id_and_source_branch_or_repo(self):
        variants=[
            ("number",123),("id",7),("url",REPO+"/pulls/123"),
            ("head.ref","random"),("base.ref","main"),
            ("base.sha","b"*40),("head.repo.id",42),
            ("head.repo.url","https://api.github.com/repos/fake/wolochain"),
        ]
        for name,value in variants:
            with self.subTest(field=name):
                target=self.pr
                bits=name.split(".")
                for bit in bits[:-1]:target=target[bit]
                old=target[bits[-1]]
                target[bits[-1]]=value
                with self.assertRaises(m.ArtifactError):self.review()
                target[bits[-1]]=old

    def test_reject_missing_reordered_or_duplicate_source(self):
        old=copy.deepcopy(self.commits)
        for variant in (
            [{"sha":"a"*40},{"sha":"b"*40},{"sha":ORIGINAL_HEAD}],
            [{"sha":SOURCE},{"sha":SOURCE},{"sha":ORIGINAL_HEAD}],
            [{"sha":SOURCE},{"sha":ORIGINAL_HEAD},{"sha":"c"*40}],
        ):
            with self.subTest(commits=variant):
                self.documents[REPO+"/pulls/124/commits?per_page=100"]=variant
                with self.assertRaises(m.ArtifactError):self.review()
        self.documents[REPO+"/pulls/124/commits?per_page=100"]=old

    def test_reject_hidden_pr_commit_pagination_or_overlimit(self):
        for count in (4,0,101):
            with self.subTest(count=count):
                self.pr["commits"]=count
                with self.assertRaises(m.ArtifactError):self.review()
        self.pr["commits"]=3

    def test_reject_unreviewed_source_and_foreign_head_branch(self):
        with self.assertRaises(m.ArtifactError):
            m._c01_authenticated_merged_pr(self.run,"f"*40,Read(self.documents))
        self.run["head_branch"]="foreign"
        with self.assertRaises(m.ArtifactError):self.review()

    def compare_fixture(self, *,base=SOURCE,builder=BUILDER,count=305):
        prefix=REPO+"/compare/"+base+"..."+builder
        template={
            "status":"ahead","behind_by":0,"ahead_by":count,
            "total_commits":count,
            "base_commit":{"sha":base},
            "merge_base_commit":{"sha":base},
        }
        a=dict(template,commits=[{"sha":"a"*40}])
        b=dict(template,commits=[{"sha":builder}])
        docs={
            prefix+"?per_page=1&page=1":a,
            prefix+"?per_page=1&page="+str(count):b,
        }
        return docs

    def test_authenticate_over_250_commits_first_and_last_page(self):
        data=self.compare_fixture()
        r=m._c01_authenticated_ancestry(SOURCE,BUILDER,Read(data))
        self.assertEqual(r["builder_commit"],BUILDER)
        self.assertEqual(r["ahead_by"],305)
        self.assertTrue(r["merged_into_builder"])

    def test_reject_false_builder_last_page(self):
        documents=self.compare_fixture()
        last=next(k for k in documents if "page=305" in k)
        documents[last]["commits"][0]["sha"]="c"*40
        with self.assertRaisesRegex(m.ArtifactError,"not comparison final"):
            m._c01_authenticated_ancestry(SOURCE,BUILDER,Read(documents))

    def test_reject_broken_server_ancestry_fields(self):
        for field,value in (("status","diverged"),("behind_by",1),
                            ("ahead_by",306),("total_commits",304),
                            ("merge_base_commit",{"sha":"a"*40}),
                            ("base_commit",{"sha":"b"*40})):
            documents=self.compare_fixture()
            first=next(k for k in documents if "page=1" in k)
            documents[first][field]=value
            with self.subTest(field=field),self.assertRaises(m.ArtifactError):
                m._c01_authenticated_ancestry(SOURCE,BUILDER,Read(documents))

    def test_reject_missing_last_page_and_oversized_ancestry(self):
        docs=self.compare_fixture()
        last=next(k for k in docs if "page=305" in k)
        docs.pop(last)
        with self.assertRaises(m.ArtifactError):
            m._c01_authenticated_ancestry(SOURCE,BUILDER,Read(docs))
        a=self.compare_fixture(count=1001)
        with self.assertRaisesRegex(m.ArtifactError,"unbounded builder"):
            m._c01_authenticated_ancestry(SOURCE,BUILDER,Read(a))

    def test_identity_ancestry_is_not_a_funded_permit(self):
        r=m._c01_authenticated_ancestry(SOURCE,SOURCE,Read({}))
        self.assertEqual(r["ahead_by"],0)
        self.assertTrue(r["merged_into_builder"])
        self.assertNotIn("financial_release_authorized",r)
        self.assertNotIn("funded_authorized",r)

if __name__=="__main__":
    unittest.main()
