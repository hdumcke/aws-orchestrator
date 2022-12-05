import sys
from aws_orchestrator.orchestrator import AWSOrchestrator as aws


def main():
    if len(sys.argv) != 2:
        print("Usage %s <config.yaml>" % sys.argv[0])
        sys.exit(1)
    env = aws(sys.argv[1])
    env.list_ip_addesses()


if __name__ == '__main__':
    main()
