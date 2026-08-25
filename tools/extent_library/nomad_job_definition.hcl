job "create-extent-library" {
  datacenters = ["dc1"]
  type        = "batch"

  constraint {
    attribute = "${node.class}"
    value     = "linux"
  }

  parameterized {
    meta_required = [
      "src_library_path",
      "dst_library_path",
      "submodels_path",
      "glcr_token"
    ]

  }

  group "create-extent-library-group" {
    restart {
      attempts = 0
      mode     = "fail"
    }

    task "processor" {
      driver = "docker"

      config {
        image = "registry.sh.nextgenwaterprediction.com/ngwpc/fim-c/flows2fim_extents:extent-library"
        force_pull = true

        auth {
          username = "ReadOnly_NGWPC_Group_Deploy_Token"
          password = "${NOMAD_META_glcr_token}"
        }

        args = [
          "-src", "${NOMAD_META_src_library_path}",
          "-dst", "${NOMAD_META_dst_library_path}",
          "-submodels", "${NOMAD_META_submodels_path}"
        ]

        logging {
          type = "awslogs"
          config {
            awslogs-group        = "/aws/ec2/nomad-client-linux-test"
            awslogs-region       = "us-east-1"
            awslogs-stream       = "${NOMAD_JOB_ID}"
            awslogs-create-group = "true"
          }
        }
      }

      resources {
        memory = 14000
      }

      logs {
        max_files     = 5
        max_file_size = 10 # MB
      }
    }
  }
}