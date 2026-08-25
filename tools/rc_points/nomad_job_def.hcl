job "create-rc-points" {
  datacenters = ["dc1"]
  type        = "batch"

  constraint {
    attribute = "${node.class}"
    value     = "linux"
  }

  parameterized {
    meta_required = [
      "collection_id",
      "root_dir_path",
      "output_dir_path",
      "glcr_token"
    ]

  }

  group "create-rc-points-group" {
    restart {
      attempts = 0
      mode     = "fail"
    }

    task "processor" {
      driver = "docker"

      config {
        image = "registry.sh.nextgenwaterprediction.com/ngwpc/ripple1d-pipeline:rc-points"
        force_pull = true

        auth {
          username = "ReadOnly_NGWPC_Group_Deploy_Token"
          password = "${NOMAD_META_glcr_token}"
        }

        args = [
          "-c", "${NOMAD_META_collection_id}",
          "-root", "${NOMAD_META_root_dir_path}",
          "-o", "${NOMAD_META_output_dir_path}",
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
        memory = 2000
      }

      logs {
        max_files     = 5
        max_file_size = 10 # MB
      }
    }
  }
}