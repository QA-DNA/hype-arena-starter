import unittest
from protocol import Protocol,kleene,ProtocolError
from bench import fact_for

class Semantics(unittest.TestCase):
    def setUp(self):
        self.protocol=Protocol({'subjects':[{'name':'Atlas','aliases':['A'],'attributes':['price','customers']},{'name':'Boreal','attributes':['customers']}]},{'attributes':{'customers':'customer count'}})
    def test_nested_unknown_short_circuit(self):
        false={'type':'recorded','state':'false'};unknown={'type':'recorded','state':'unsure'};true={'type':'recorded','state':'true'}
        lookup=lambda n:n['state']
        self.assertEqual(kleene({'type':'all','children':[false,unknown]},lookup),'false')
        self.assertEqual(kleene({'type':'any','children':[true,unknown]},lookup),'true')
        self.assertEqual(kleene({'type':'not','child':unknown},lookup),'unsure')
    def test_named_and_ordinal_mean_same_descriptor(self):
        named={'evidence_policy':'provided_notes_only','context':[],'text':"Using only the supplied notes, all of these statements are true: (the entry for Atlas's customer count in the note of 2 March 2026 reads 5 customers). A bus ticket has 79 on it."}
        tree=self.protocol.parse(named)
        leaf=tree['children'][0];self.assertEqual(leaf['literal'],"Atlas's customers is 5 customers.")
        ordinal={'evidence_policy':'provided_notes_only','context':[{'id':'binding-p-1','role':'discourse','text':"Here, note one means the note about Atlas's customer count dated 2 March 2026."}],'text':'Using only the supplied notes, it is not true that (all of these statements are true: (note one records 5 customers for that entry)).'}
        ref=self.protocol.parse(ordinal)['child']['children'][0]['reference']
        self.assertEqual({k:ref[k] for k in ('subject','attribute','date')},{k:leaf['reference'][k] for k in ('subject','attribute','date')})
    def test_unprovided_note_stays_missing_even_when_extraction_is_cached(self):
        parsed={'source':{'facts':[{'subject':'Atlas','attribute':'customers','value':{'kind':'quantity','value':5,'unit':'customer'}}]}}
        ref={'subject':'Atlas','attribute':'customers','date':'2026-03-02','source_id':None}
        self.assertEqual(fact_for(ref,[],parsed),(None,None))
        self.assertIsNotNone(fact_for(ref,[{'source_id':'p-1','date':'2026-03-02','request_id':'source'}],parsed)[1])
        self.assertEqual(fact_for({**ref,'date':'2026-03-03'},[{'source_id':'p-1','date':'2026-03-02','request_id':'source'}],parsed),(None,None))
    def test_comparison_operator_and_declared_source_binding(self):
        inp={'evidence_policy':'provided_notes_only','context':[],'text':"Using only the supplied notes, at least one of these statements is true: (the value recorded for Atlas's customer count on 2 March 2026 is no lower than the value recorded for Boreal's customer count on 3 March 2026); (the entry for Atlas's customer count in the note of 2 March 2026 reads 9 customers)."}
        tree=self.protocol.parse(inp);self.assertEqual(tree['type'],'any');self.assertEqual(tree['children'][0]['op'],'ge')
    def test_unrecognized_or_ambiguous_reference_is_not_guessed(self):
        inp={'evidence_policy':'provided_notes_only','context':[],'text':'Using only the supplied notes, all of these statements are true: (note one records 5 customers for that entry).'}
        with self.assertRaises(ProtocolError):self.protocol.parse(inp)
    def test_public_source_specific_vocabulary_uses_only_known_attribute_names(self):
        p=Protocol({'subjects':[{'name':'Atlas','attributes':['customers']}]},{'source_attribute_words':{'p-1':'subscriber head count'}},{'p-1':{'customers'}})
        self.assertEqual(p.descriptor('Atlas','subscriber head count','2 March 2026')['attribute'],'customers')
        self.assertEqual(p.descriptor('Atlas','subscriber head count status','2 March 2026')['attribute'],'customers')

if __name__=='__main__':unittest.main()
