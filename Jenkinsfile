pipeline {
    agent any
    stages {
        stage('Checkout Code') {
            steps {
                // Pulls code from your GitHub
                checkout scm
            }
        }
        stage('SonarQube Analysis') {
            steps {
                script {
                    // The 'tool' name must match what we saved in Global Tool Config
                    def scannerHome = tool 'SonarQube-Scanner'

                    // The 'env' name must match what we saved in System Config
                    withSonarQubeEnv('SonarQube-Server') {
                        sh "${scannerHome}/bin/sonar-scanner"
                    }
                }
            }
        }
    }
}