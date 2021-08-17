from tests.helm_template_generator import render_chart
import jmespath, pytest 

chart_files = [
  "charts/alertmanager/templates/alertmanager-statefulset.yaml",
  "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
  ]


supported_global_storage_options = ["-","astrosc"]
@pytest.mark.parametrize(
    "supported_types",
    supported_global_storage_options
)


def test_alertmanager_global_storageclass(supported_types):
    """Test globalstorageclass feature of alertmanager statefulset template"""
    for file in chart_files :
      docs = render_chart(
          values={"global": {"storageClass": supported_types}},
          show_only=[file],
      )
      assert len(docs) == 1
      doc = docs[0]
      
      if supported_types == "-":
          print("test for -", file)
          assert doc["spec"]["volumeClaimTemplates"][0]["spec"]["storageClassName"] == ""
  
      if supported_types == "astrosc":
          print("test for astroc", file)
          assert (
              doc["spec"]["volumeClaimTemplates"][0]["spec"]["storageClassName"]
              == "astrosc"
          )
